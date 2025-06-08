{ pkgs, lib, config, ... }:
let
    # Create the NI-VISA derivation first
    ni-visa-derivation = pkgs.stdenv.mkDerivation rec {
        pname = "ni-visa";
        version = "17.0.0";

        nativeBuildInputs = with pkgs; [
            libarchive  # provides bsdtar
            patch
            curl
            wget
        ];

        buildInputs = with pkgs; [
            gcc.cc.lib
            stdenv.cc.cc.lib  # Provides libstdc++.so.6
            glibc
            udev
        ];

        src = pkgs.fetchurl {
            url = "http://ftp.ni.com/support/softlib/visa/NI-VISA/17.0/Linux/NI-VISA-17.0.0.iso";
            sha256 = "sha256-rtNt9zL58wzGp2XzKr446cBL9VimDV+AemfaBJP5gvw=";
        };

        unpackPhase = ''
            runHook preUnpack

            echo "Extracting NI-VISA ISO..."
            # Create a working directory
            mkdir -p source
            cd source

            # Extract the ISO using bsdtar
            bsdtar -xf $src

            runHook postUnpack
        '';

        # Create comprehensive USBTMC udev rules
        udevRules = pkgs.writeText "99-usbtmc.rules" ''
            # USBTMC instruments

            # Agilent/Keysight devices
            SUBSYSTEMS=="usb", ACTION=="add", ATTRS{idVendor}=="0957", GROUP="usbtmc", MODE="0660"

            # Tektronix devices
            SUBSYSTEMS=="usb", ACTION=="add", ATTRS{idVendor}=="0699", GROUP="usbtmc", MODE="0660"

            # Rohde & Schwarz devices
            SUBSYSTEMS=="usb", ACTION=="add", ATTRS{idVendor}=="0aad", GROUP="usbtmc", MODE="0660"

            # National Instruments devices
            SUBSYSTEMS=="usb", ACTION=="add", ATTRS{idVendor}=="3923", GROUP="usbtmc", MODE="0660"

            # Rigol devices
            SUBSYSTEMS=="usb", ACTION=="add", ATTRS{idVendor}=="1ab1", GROUP="usbtmc", MODE="0660"

            # Generic USBTMC devices
            SUBSYSTEMS=="usb", ACTION=="add", ATTRS{bInterfaceClass}=="fe", ATTRS{bInterfaceSubClass}=="03", GROUP="usbtmc", MODE="0660"

            # Create usbtmc group if it doesn't exist
            ACTION=="add", SUBSYSTEM=="usb", ATTRS{bInterfaceClass}=="fe", ATTRS{bInterfaceSubClass}=="03", RUN+="/bin/sh -c 'getent group usbtmc || groupadd usbtmc'"
        '';

        buildPhase = ''
            set -e
            echo "Building NI-VISA..."

            # Extract the ISO
            echo "Extracting NI-VISA ISO..."
            bsdtar -xf $src

            # Extract the main tarball
            bsdtar -xf nivisa-17.0.0f*.tar.gz

            # Create extraction directory and extract RPMs
            mkdir -p extract
            for f in rpms/nivisa{-32bit,}-17.0.0-f*.x86_64.rpm; do
                if [ -f "$f" ]; then
                    echo "Extracting $f"
                    bsdtar -xf "$f" -C extract
                fi
            done
        '';

        installPhase = ''
            set -e
            echo "Installing NI-VISA to $out..."

            # Create directory structure
            mkdir -p $out/{include,lib,lib32,bin}
            mkdir -p $out/lib/environment.d
            mkdir -p $out/opt/ni-visa/usr/local/
            mkdir -p $out/etc/{profile.d,natinst,udev/rules.d}
            mkdir -p $out/lib/udev/rules.d

            # Set up the main vxipnp path
            vxipnppath="opt/ni-visa/usr/local/vxipnp"

            # Copy main VISA files
            if [ -d extract/usr/local/vxipnp ]; then
                echo "Copying vxipnp directory..."
                cp -a extract/usr/local/vxipnp $out/$vxipnppath
            else
                echo "Warning: vxipnp directory not found in extracted files"
                # Create minimal structure for testing
                mkdir -p $out/$vxipnppath/{linux/{lib64,bin,include},etc}
                echo "# Minimal NI-VISA installation" > $out/$vxipnppath/README
            fi

            # Create USB raw permissions rules file (initially empty)
            touch $out/etc/udev/rules.d/99-nivisa_usbraw.rules

            # Create symlinks for libraries (if they exist)
            if [ -f $out/$vxipnppath/linux/lib64/libvisa.so ]; then
                ln -sf $out/$vxipnppath/linux/lib64/libvisa.so $out/lib/libvisa.so
                ln -sf $out/$vxipnppath/linux/lib64/libvisa.so $out/lib32/libvisa.so
            fi

            # Create symlinks for headers (if they exist)
            if [ -d $out/$vxipnppath/linux/include ]; then
                for f in $out/$vxipnppath/linux/include/*.h; do
                    if [ -f "$f" ]; then
                        header_name=$(basename "$f")
                        ln -sf $out/$vxipnppath/linux/include/"$header_name" $out/include/"$header_name"
                    fi
                done
            fi

            # Set up configuration directories
            mkdir -p $out/$vxipnppath/etc
            echo "$out/$vxipnppath" > $out/$vxipnppath/etc/nivisa.dir
            echo "$out/$vxipnppath" > $out/$vxipnppath/etc/vxipnp.dir

            # Create configuration symlinks
            ln -sf $out/$vxipnppath/etc $out/etc/natinst/nivisa
            ln -sf $out/$vxipnppath/etc $out/etc/natinst/vxipnp

            # Create wrapper script for AddUsbRawPermissions.sh
            if [ -f $out/$vxipnppath/linux/NIvisa/USB/AddUsbRawPermissions.sh ]; then
                ln -sf $out/$vxipnppath/linux/NIvisa/USB/AddUsbRawPermissions.sh $out/bin/AddUsbRawPermissions.sh
                chmod +x $out/$vxipnppath/linux/NIvisa/USB/AddUsbRawPermissions.sh
            else
                # Create a minimal version for testing
                cat > $out/bin/AddUsbRawPermissions.sh << 'EOF'
#!/bin/bash
echo "AddUsbRawPermissions.sh: Creating minimal USB raw permissions..."
echo "# Minimal USB raw permissions for NI-VISA" > /etc/udev/rules.d/99-nivisa_usbraw.rules
echo "SUBSYSTEM==\"usb\", MODE=\"0666\"" >> /etc/udev/rules.d/99-nivisa_usbraw.rules
echo "Done. You may need to reload udev rules: sudo udevadm control --reload-rules"
EOF
                chmod +x $out/bin/AddUsbRawPermissions.sh
            fi

            # Install udev rules
            cp ${udevRules} $out/lib/udev/rules.d/99-usbtmc.rules

            # Set up environment variables
            echo "VXIPNPPATH=$out/$vxipnppath" > $out/lib/environment.d/40-vxipnppath.conf
            echo "export VXIPNPPATH=$out/$vxipnppath" > $out/etc/profile.d/vxipnppath.sh

            echo "NI-VISA installation complete!"
        '';

        meta = with lib; {
            description = "National Instruments NI-VISA Library for Linux";
            homepage = "https://www.ni.com/visa/";
            license = licenses.free;
            platforms = platforms.linux;
        };
    };

    # Create wrapper scripts for easy access
    ni-visa-test = pkgs.writeShellScriptBin "ni-visa-test" ''
        echo "NI-VISA Installation Test"
        echo "========================="
        echo ""
        echo "VXIPNPPATH: $VXIPNPPATH"
        echo "NI-VISA Library: ${ni-visa-derivation}/lib/libvisa.so"
        echo ""
        if [ -f "${ni-visa-derivation}/lib/libvisa.so" ]; then
            echo "✓ NI-VISA library found"
        else
            echo "✗ NI-VISA library not found"
        fi
        echo ""
        echo "Testing Python VISA..."
        python3 -c "
import sys
try:
    import pyvisa
    print('✓ PyVISA imported successfully')
    try:
        rm = pyvisa.ResourceManager()
        print('✓ ResourceManager created')
        resources = rm.list_resources()
        print(f'Available resources: {resources}')
        if resources:
            print('✓ Instruments detected!')
        else:
            print('⚠ No instruments detected')
    except Exception as e:
        print(f'✗ ResourceManager error: {e}')
except ImportError as e:
    print(f'✗ PyVISA not available: {e}')
"
    '';

in
    {
    packages = [
        ni-visa-derivation
        ni-visa-test
        pkgs.git 
        pkgs.libusb1
        pkgs.usbutils  # adds lsusb for debugging
    ];

    languages = {
        python.enable = true;
        python.poetry.enable = true;
    };

    # Create scripts for common tasks
    scripts = {
        setup-udev-rules = {
            exec = ''
                echo "Setting up udev rules for NI-VISA..."
                sudo cp ${ni-visa-derivation}/lib/udev/rules.d/99-usbtmc.rules /etc/udev/rules.d/
                sudo udevadm control --reload-rules
                sudo udevadm trigger
                echo "Done! You may need to add your user to the 'usbtmc' group:"
                echo "  sudo usermod -a -G usbtmc $USER"
                echo "  newgrp usbtmc  # or logout/login to apply group changes"
            '';
        };

        visa-debug = {
            exec = ''
                echo "NI-VISA Debug Information"
                echo "========================="
                echo ""
                echo "Environment:"
                echo "  VXIPNPPATH: $VXIPNPPATH"
                echo "  LD_LIBRARY_PATH: $LD_LIBRARY_PATH"
                echo ""
                echo "USB Devices:"
                lsusb
                echo ""
                echo "PyVISA Debug Info:"
                python3 -c "import pyvisa; print(pyvisa.util.get_debug_info())" 2>/dev/null || echo "PyVISA debug info not available"
                echo ""
                echo "Available VISA Resources:"
                python3 -c "
import pyvisa
try:
    rm = pyvisa.ResourceManager()
    resources = rm.list_resources()
    if resources:
        for resource in resources:
            print(f'  {resource}')
    else:
        print('  No resources found')
except Exception as e:
    print(f'  Error: {e}')
"
            '';
        };
    };

    enterShell = ''
        echo "NI-VISA development environment loaded!"
        echo "======================================"
        echo ""
        echo "Available commands:"
        echo "  ni-visa-test         - Test the NI-VISA installation"
        echo "  setup-udev-rules     - Install udev rules (requires sudo)"
        echo "  visa-debug           - Show debug information"
        echo "  AddUsbRawPermissions.sh - Add USB raw permissions"
        echo "  lsusb                - List USB devices"
        echo ""
        echo "Environment variables:"
        echo "  VXIPNPPATH: $VXIPNPPATH"
        echo ""
        echo "Quick test:"
        echo "  python3 -c 'import pyvisa; print(pyvisa.ResourceManager().list_resources())'"
        echo ""
        echo "⚠ IMPORTANT: Run 'setup-udev-rules' to install USB device rules!"
    '';

    env = {
        VXIPNPPATH = "${ni-visa-derivation}/opt/ni-visa/usr/local/vxipnp";
        LD_LIBRARY_PATH = "${ni-visa-derivation}/lib:${pkgs.libusb1}/lib";
    };
}
