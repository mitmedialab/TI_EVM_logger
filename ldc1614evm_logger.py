#!/usr/bin/env python3
"""
Log inductive sensor data from TI's LDC1614 EVM.

Date: 18 October 2017
Author: Scott Johnston
"""

import serial, serial.tools.list_ports
import crcmod.predefined
import binascii
import struct
import time
import tables

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
RCOUNT_SETTING        = 0xFFFF      # Very conservative
SETTLECOUNT_SETTING   = 0x1000      # Conservative, probably could be smaller
CLOCK_DIVIDER_SETTING = 0x1001      # f_in = 1, f_ref = 1
CONFIG_SETTING        = 0x1E01      # Ext clock, override R_p, disable auto amp
MUX_CONFIG_SETTING    = 0x820C      # Continuously scan channels 0 and 1, 3.3 MHz deglitch
DRIVE_CURRENT_SETTING = 0x6B40      # Magical value from GUI tool

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
        raise RuntimeError('Uh-oh, command returned an error.')
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
        raise RuntimeError('Uh-oh, command returned an error.')
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
        raise RuntimeError('Uh-oh, command returned an error.')
    return

def read_stream(serial_port):
    stream_bytes = serial_port.read(32)
    if DEBUG_PRINT_RX_DATA:
        print("< " + ":".join("{:02x}".format(c) for c in stream_bytes))
    (error_code, raw_ch0, raw_ch1, raw_ch2, raw_ch3) = struct.unpack('>3xB2xLLLL10x', stream_bytes)
    if error_code:
        raise RuntimeError('Uh-oh, command returned an error.')
    return raw_ch0, raw_ch1, raw_ch2, raw_ch3

def ldc_config(serial_port):
    # Put the LDC1614 into sleep mode
    write_reg(serial_port, LDC1614_CONFIG, SLEEP_MODE)
    # Set RCOUNT and settling count to configure conversion time
    write_reg(serial_port, LDC1614_RCOUNT_CH0, RCOUNT_SETTING)
    write_reg(serial_port, LDC1614_RCOUNT_CH1, RCOUNT_SETTING)
    write_reg(serial_port, LDC1614_SETTLECOUNT_CH0, SETTLECOUNT_SETTING)
    write_reg(serial_port, LDC1614_SETTLECOUNT_CH1, SETTLECOUNT_SETTING)
    # Set clock dividers
    write_reg(serial_port, LDC1614_CLOCK_DIVIDERS_CH0, CLOCK_DIVIDER_SETTING)
    write_reg(serial_port, LDC1614_CLOCK_DIVIDERS_CH1, CLOCK_DIVIDER_SETTING)
    # Set sensor current
    write_reg(serial_port, LDC1614_DRIVE_CURRENT_CH0, DRIVE_CURRENT_SETTING)
    write_reg(serial_port, LDC1614_DRIVE_CURRENT_CH1, DRIVE_CURRENT_SETTING)
    # Set channels to scan
    write_reg(serial_port, LDC1614_MUX_CONFIG, MUX_CONFIG_SETTING)
    # Put it back into normal operating mode
    write_reg(serial_port, LDC1614_CONFIG, CONFIG_SETTING)

def main():
    # Identify LDC1614 EVM by USB VID/PID match
    detected_ports = list(serial.tools.list_ports.grep('2047:08F8'))
    if not detected_ports:
        raise RuntimeError('No EVM found.')
    else:
        # open the serial device.
        evm = serial.Serial(detected_ports[0].device, 115200, timeout=1)

    device_id = read_reg(evm, LDC1614_DEVICE_ID)
    ldc_config(evm)

    h5f = tables.open_file('ldc1614evm_output.h5', 'w')
    description_name = {
        'unixtime': tables.Time64Col(),
        'data_ch0': tables.UInt32Col()
    }
    tbl = h5f.create_table('/', 'drift_data', description_name)

    start_stream(evm)
    while True:
        (raw_ch0, raw_ch1, raw_ch2, raw_ch3) = read_stream(evm)
        if raw_ch0 and not (raw_ch0 & 0xF0000000):
            tbl.row['unixtime'] = time.time()
            tbl.row['data_ch0'] = raw_ch0
            tbl.row.append()
            tbl.flush()

    # If we handled errors like KeyboardInterrupt properly, we'd get here:
    tbl.close()
    h5f.close()

if __name__ == "__main__":
    main()
