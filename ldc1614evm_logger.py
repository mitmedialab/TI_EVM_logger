#!/usr/bin/env python3
"""Log inductive sensor data from TI's LDC1614 EVM."""

__author__ = 'Scott Johnston'
__version__ = '0.0.2'
__date__ = "15 January 2018"

import serial, serial.tools.list_ports
import crcmod.predefined
import binascii
import struct
import time
import tables
import argparse

# LDC1614 register addresses (do not change)
LDC1614_RCOUNT_CH0          = 0x08
LDC1614_RCOUNT_CH1          = 0x09
LDC1614_SETTLECOUNT_CH0     = 0x10
LDC1614_SETTLECOUNT_CH1     = 0x11
LDC1614_CLOCK_DIVIDERS_CH0  = 0x14
LDC1614_CLOCK_DIVIDERS_CH1  = 0x15
LDC1614_STATUS              = 0x18
LDC1614_ERROR_CONFIG        = 0x19
LDC1614_CONFIG              = 0x1A
LDC1614_MUX_CONFIG          = 0x1B
LDC1614_RESET_DEV           = 0x1C
LDC1614_DRIVE_CURRENT_CH0   = 0x1E
LDC1614_DRIVE_CURRENT_CH1   = 0x1F
LDC1614_MANUFACTURER_ID     = 0x7E
LDC1614_DEVICE_ID           = 0x7F

# Debug controls
DEBUG_PRINT_TX_DATA = False
DEBUG_PRINT_RX_DATA = False
DEBUG_PRINT_READ_DATA = False

# Our LDC1614 settings
SLEEP_MODE            = 0x2801
CONFIG_SETTING        = 0x1E01      # Ext clock, override R_p, disable auto amp

config_singlechannel = {
    LDC1614_RCOUNT_CH0:         0xFFFF,
    LDC1614_RCOUNT_CH1:         0x0004, # CH1 is set up in dummy mode here.
    LDC1614_SETTLECOUNT_CH0:    0x8692,
    LDC1614_SETTLECOUNT_CH1:    0x0001,
    LDC1614_CLOCK_DIVIDERS_CH0: 0x1001,
    LDC1614_CLOCK_DIVIDERS_CH1: 0x1001,
    LDC1614_DRIVE_CURRENT_CH0:  0x4A40, # Idrive=9
    LDC1614_DRIVE_CURRENT_CH1:  0x4A40, # Idrive=9
    LDC1614_MUX_CONFIG:         0x820D  # Continuously scan channels 0 and 1, 10 MHz deglitch
}

def send_command(serial_port, command_bytes):
    crc8 = crcmod.predefined.mkCrcFun('crc-8')
    # command_bytes = bytes.fromhex(command_string)
    crc_byte = bytes([crc8(command_bytes)])
    output_bytes = command_bytes + crc_byte
    if DEBUG_PRINT_TX_DATA:
        print("> " + ":".join("{:02x}".format(c) for c in output_bytes))
    serial_port.write(output_bytes)
    response_bytes = serial_port.read(32)
    if DEBUG_PRINT_RX_DATA:
        print("< " + ":".join("{:02x}".format(c) for c in response_bytes))
    (error_code, register_value) = struct.unpack('>3xB2xH24x', response_bytes)
    if error_code:
        raise RuntimeError('1- Uh-oh, command returned an error.')
    return register_value

def write_reg(serial_port, addr, data):
    command_bytes = bytes.fromhex('4C150100042A') + addr.to_bytes(1, byteorder='big') + data.to_bytes(2, byteorder='big') # addr is 1 byte, data is 2 bytes MSB 1st
    send_command(serial_port, command_bytes)

def read_reg(serial_port, addr):
    # command_string = '4C150100022A' + addr # which register should I get?
    command_bytes = bytes.fromhex('4C150100022A') + addr.to_bytes(1, byteorder='big') # which register should I get?
    send_command(serial_port, command_bytes)
    # command_string = '4C140100022A02'           # read register command
    command_bytes = bytes.fromhex('4C140100022A02')           # read register command
    register_value = send_command(serial_port, command_bytes)
    if DEBUG_PRINT_READ_DATA:
        print("Addr:", addr, "Data:", register_value)
    return register_value

def start_stream(serial_port):
    output_bytes = bytes.fromhex('4C0501000601290404302AC1')
    if DEBUG_PRINT_TX_DATA:
        print("> " + ":".join("{:02x}".format(c) for c in output_bytes))
    serial_port.write(output_bytes)
    response_bytes = serial_port.read(32)
    if DEBUG_PRINT_RX_DATA:
        print("< " + ":".join("{:02x}".format(c) for c in response_bytes))
    error_code = struct.unpack('>3xB28x', response_bytes)[0]
    if error_code:
        raise RuntimeError('2- Uh-oh, command returned an error.')
    return

def stop_stream(serial_port):
    output_bytes = bytes.fromhex('4C0601000101D2')
    if DEBUG_PRINT_TX_DATA:
        print("> " + ":".join("{:02x}".format(c) for c in output_bytes))
    serial_port.write(output_bytes)
    response_bytes = serial_port.read(32)
    if DEBUG_PRINT_RX_DATA:
        print("< " + ":".join("{:02x}".format(c) for c in response_bytes))
    error_code = struct.unpack('>3xB28x', response_bytes)[0]
    if error_code:
        raise RuntimeError('3- Uh-oh, command returned an error.')
    return

def read_stream(serial_port):
    stream_bytes = serial_port.read(32)
    if DEBUG_PRINT_RX_DATA:
        print("< " + ":".join("{:02x}".format(c) for c in stream_bytes))
    (error_code, raw_ch0, raw_ch1, raw_ch2, raw_ch3) = struct.unpack('>3xB2xLLLL10x', stream_bytes)
    if error_code:
        raise RuntimeError('4- Uh-oh, command returned an error.')
    return raw_ch0, raw_ch1, raw_ch2, raw_ch3

def ldc_config(serial_port):
    # Put the LDC1614 into sleep mode
    write_reg(serial_port, LDC1614_CONFIG, SLEEP_MODE)
    # Write channel configurations
    for k,v in config_singlechannel.items():
        write_reg(serial_port, k, v)
    # Put it back into normal operating mode
    write_reg(serial_port, LDC1614_CONFIG, CONFIG_SETTING)

def main(filename):
    # Identify LDC1614 EVM by USB VID/PID match
    detected_ports = list(serial.tools.list_ports.grep('2047:08F8'))
    if not detected_ports:
        raise RuntimeError('No EVM found.')
    else:
        # open the serial device.
        evm = serial.Serial(detected_ports[0].device, 115200, timeout=1)

    device_id = read_reg(evm, LDC1614_DEVICE_ID)
    ldc_config(evm)

    h5f = tables.open_file(filename, 'a', title="LDC1614EVM Logger Data")

    try:
        tbl = h5f.get_node('/logdata')
        print("Appending existing table in: {}".format(filename))
    except tables.NoSuchNodeError:
        table_definition = {
            'time_utc': tables.Time64Col(),
            'data_ch0': tables.UInt32Col(),
            'data_ch1': tables.UInt32Col()
        }
        tbl = h5f.create_table('/', 'logdata', description=table_definition, title='LDC1614 dataset')
        print("Created new table in: {}".format(filename))

    
    start_stream(evm)
    print("Beginning logging...")
    while True:
        (raw_ch0, raw_ch1, raw_ch2, raw_ch3) = read_stream(evm)
        if raw_ch0 and not (raw_ch0 & 0xF0000000):
            tbl.row['time_utc'] = time.time()
            tbl.row['data_ch0'] = raw_ch0
            tbl.row['data_ch1'] = raw_ch1
            tbl.row.append()
            tbl.flush()

    # If we handled errors like KeyboardInterrupt properly, we'd get here:
    print("Cleaning up...")
    tbl.close()
    h5f.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('filename', nargs='?', help="Output file (HDF5 format)", default='data.h5')
    args = parser.parse_args()

    main(args.filename)
