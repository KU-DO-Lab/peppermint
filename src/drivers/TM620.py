__author__ = "Jenfrey Gudger"
__credits__ = ["Jenfrey Gudger"]
__maintainer__ = "Jenfrey Gudger"
__email__ = "jgudger@cryomagnetics.com"

import serial
import time
import socket
import threading


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(SingletonMeta, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class SerialConnection(metaclass=SingletonMeta):
    def __init__(self, port, baud_rate=9600, timeout=1):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.serial_connection = None
        self.lock = threading.Lock()


    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def open(self):
        with self.lock:
            if not self.serial_connection:
                self.serial_connection = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
                self.serial_connection.flushInput()
                self.serial_connection.flushOutput()

    def close(self):
        with self.lock:
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.flushInput()
                self.serial_connection.flushOutput()
                self.serial_connection.reset_input_buffer()
                self.serial_connection.reset_output_buffer()
                self.serial_connection.flush()
                self.clear_buffer()
                self.serial_connection.close()
                self.serial_connection = None

    def write(self, data):
        with self.lock:
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.flushInput()
                self.serial_connection.flushOutput()
                self.serial_connection.write(data.encode())
                self.serial_connection.flushInput()
                self.serial_connection.flushOutput()

    def read(self, num_bytes=1024):
        with self.lock:
            if self.serial_connection and self.serial_connection.is_open:
                num_bytes = self.serial_connection.inWaiting()
                response = self.serial_connection.read(num_bytes).decode().strip()
                self.serial_connection.flushOutput()
                self.serial_connection.flushInput()
                return response

    def clear_buffer(self):
        with self.lock:
            if self.serial_connection and self.serial_connection.is_open:
                num_bytes=6
                self.serial_connection.flushInput()
                self.serial_connection.flushOutput()
                while num_bytes > 5:
                    self.serial_connection.write("*wai\n".encode())
                    time.sleep(1)
                    num_bytes = self.serial_connection.inWaiting()
                self.serial_connection.flushInput()
                self.serial_connection.flushOutput()

    def read_until(self, delim):
        with self.lock:
            if self.serial_connection and self.serial_connection.is_open:
                return self.serial_connection.read_until('{}'.format(delim).encode()).decode().strip()

def socket_send_ascii_message(ip, port, message, read=True, timeout=4):
    # Create a socket object
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        # Set a timeout for the connection
        client_socket.settimeout(timeout)
        
        # Connect to the device
        print(ip,port)
        client_socket.connect((ip, port))
        
        # Send the ASCII message
        time.sleep(0.1)
        client_socket.send((message+"\n").encode())
        
        if read:
        # Receive the response (optional)
            time.sleep(0.1)
            response = str(client_socket.recv(1024).decode()).strip()
            return response
        else:
            return f"read={read}"
        
    except socket.error as e:
        print("Socket error:", str(e))
        return e
        
    finally:
        # Close the socket
        client_socket.close()

def serial_send_ascii_message(com_port=None,message=None, read=True,baud_rate=9600,timeout=3):
    serial_connection = SerialConnection(com_port,timeout=timeout,baud_rate=baud_rate)
    # Connect to the device
    serial_connection.open()
    
    # Send the ASCII message
    time.sleep(0.1)
    serial_connection.write(message+"\n")
    
    if read:
    # Receive the response (optional)
        time.sleep(0.1)
        response = str(serial_connection.read()).strip().replace(message,"").strip()
        response = response.strip()
        return response
    else:
        return f"read={read}"

class TM620Connection:
    def __init__(self, ip=None, port=None, com_port=None):
        self.ip = ip
        self.port = port
        self.com_port = com_port
        self.connection = None

    def send_ascii_message_(self, command, read=True):
        if self.ip and self.port:
            return socket_send_ascii_message(self.ip, self.port, command, read)
        elif self.com_port:
            return serial_send_ascii_message(com_port=self.com_port, message=command, read=read)

    def get_curve(self):
        return self.send_ascii_message_("curve?")

    def get_error(self):
        return self.send_ascii_message_("error?")

    def get_excitation_mode(self):
        return self.send_ascii_message_("exc?")

    def get_high_alarm(self):
        return self.send_ascii_message_("h-alm?")

    def get_low_alarm(self):
        return self.send_ascii_message_("l-alm?")

    def get_measurement(self,subchannel=""):
        return self.send_ascii_message_(f"meas? {subchannel}")

    def get_subchannel_name(self):
        return self.send_ascii_message_("name?")

    def get_current_subchannel(self):
        return self.send_ascii_message_("subch?")

    def get_units(self):
        return self.send_ascii_message_("units?")        

    def get_status(self):
        return self.send_ascii_message_("stat?")

    def _get_ese_mask_(self):
        return self.send_ascii_message_("*ESE?")

    def _get_esr_mask_(self):
        return self.send_ascii_message_("*ESR?")

    def get_id(self):
        return self.send_ascii_message_("*IDN?")

    def _get_sre_mask_(self):
        return self.send_ascii_message_("*SRE?")

    def _get_status_byte_(self):
        return self.send_ascii_message_("*STB?")

    def set_curve(self,curve_index):
        return self.send_ascii_message_(f"curve {curve_index}",read=False)

    def set_error(self,error_mode):
        return self.send_ascii_message_(f"error {error_mode}",read=False)

    def set_excitation_mode(self,mode):
        return self.send_ascii_message_(f"exc {mode}",read=False)

    def set_high_alarm(self,degrees):
        return self.send_ascii_message_(f"h-alm {degrees}",read=False)

    def set_low_alarm(self,degrees):
        return self.send_ascii_message_(f"l-alm {degrees}",read=False)

    def set_subchannel_name(self,name_string):
        return self.send_ascii_message_(f"name {name_string}",read=False)

    def set_current_subchannel(self,channel):
        return self.send_ascii_message_(f"subch {channel}",read=False)

    def set_units(self,unit_selection):
        return self.send_ascii_message_(f"units {unit_selection}",read=False)

    def set_local(self):
        return self.send_ascii_message_("local",read=False)

    def set_remote(self):
        return self.send_ascii_message_("remote",read=False)

    def set_remote_lock(self):
        return self.send_ascii_message_("rwlock",read=False)

    def _clear_esr_(self):
        return self.send_ascii_message_("*CLS")

    def _set_ese_mask_(self,mask):
        return self.send_ascii_message_(f"*ESE {mask}")

    def reset(self,hw=""):
        return self.send_ascii_message_(f"*RST {hw}")

    def _set_sre_mask_(self,mask):
        return self.send_ascii_message_(f"*SRE? {mask}")

    def __del__(self):
        try:
            self.set_local()
            self.connection.close()
        except:
            pass

if __name__ == "__main__":
    ##EXAMPLES##
    
    ##Example power supply object creation (socket)
    tm=TM620Connection(ip="192.168.1.55",port=7777)
    
    ##Example power supply object creation (serial)
    tm=TM620Connection(com_port="COM24")
    
    ##Example power supply function call
    print(f"Tempature Reading: {tm.get_measurement()}")
    
    ##Example direct command
    tm.send_ascii_message_("remote")
    print("Remote mode set.")
    time.sleep(3)
    tm.send_ascii_message_("local")
    print("Remote mode disabled.")
    print()
