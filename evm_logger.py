#!/usr/bin/env python3
"""Log inductive sensor data from TI's EVM boards (tested with FDC2214 and LDC1614)."""

host = "127.0.0.1"
port = 8080

filename = "data.h5"

import serial, serial.tools.list_ports
import crcmod.predefined
import binascii
import struct
import time
import tables
import argparse
import math
import asyncio
import websockets

# register addresses (do not change)
EVM_RCOUNT_CH0          = 0x08
EVM_RCOUNT_CH1          = 0x09
EVM_RCOUNT_CH2          = 0x0a
EVM_RCOUNT_CH3          = 0x0b
EVM_SETTLECOUNT_CH0     = 0x10
EVM_SETTLECOUNT_CH1     = 0x11
EVM_SETTLECOUNT_CH2     = 0x12
EVM_SETTLECOUNT_CH3     = 0x13
EVM_CLOCK_DIVIDERS_CH0  = 0x14
EVM_CLOCK_DIVIDERS_CH1  = 0x15
EVM_CLOCK_DIVIDERS_CH2  = 0x16
EVM_CLOCK_DIVIDERS_CH3  = 0x17
EVM_STATUS              = 0x18
EVM_ERROR_CONFIG        = 0x19
EVM_CONFIG              = 0x1A
EVM_MUX_CONFIG          = 0x1B
EVM_RESET_DEV           = 0x1C
EVM_DRIVE_CURRENT_CH0   = 0x1E
EVM_DRIVE_CURRENT_CH1   = 0x1F
EVM_DRIVE_CURRENT_CH2   = 0x20
EVM_DRIVE_CURRENT_CH3   = 0x21
EVM_MANUFACTURER_ID     = 0x7E
EVM_DEVICE_ID           = 0x7F

# Debug controls
DEBUG_PRINT_TX_DATA = False
DEBUG_PRINT_RX_DATA = False
DEBUG_PRINT_READ_DATA = False

# Our settings
SLEEP_MODE            = 0x2801
CONFIG_SETTING        = 0x1E01      # Ext clock, override R_p, disable auto amp

config_multichannel = {
    EVM_RCOUNT_CH0:         0xFFFF, # TODO: tune these if noise pbs occur!
    EVM_RCOUNT_CH1:         0xFFFF,
    EVM_RCOUNT_CH2:         0xFFFF,
    EVM_RCOUNT_CH3:         0xFFFF,
    EVM_SETTLECOUNT_CH0:    0x0001,
    EVM_SETTLECOUNT_CH1:    0x0001,
    EVM_SETTLECOUNT_CH2:    0x0001,
    EVM_SETTLECOUNT_CH3:    0x0001,
    EVM_CLOCK_DIVIDERS_CH0: 0x1001,
    EVM_CLOCK_DIVIDERS_CH1: 0x1001,
    EVM_CLOCK_DIVIDERS_CH2: 0x1001,
    EVM_CLOCK_DIVIDERS_CH3: 0x1001,
    EVM_DRIVE_CURRENT_CH0:  0xF800, # TODO: measure oscillation amplitude on an
    EVM_DRIVE_CURRENT_CH1:  0xF800, # oscilloscope and adjust this IDRIVE value
    EVM_DRIVE_CURRENT_CH2:  0xF800, # See p42 of datasheet
    EVM_DRIVE_CURRENT_CH3:  0xF800,
    EVM_MUX_CONFIG:         0xC20D  # Continuously scan channels 0 to 3, 10 MHz deglitch
#bit: 1 1 1 1   1 1 0 0    0 0 0 0   0 0 0 0
#     5 4 3 2   1 0 9 8    7 6 5 4   3 2 1 0
#
#bin: 1 1 0 0   0 0 1 0    0 0 0 0   1 1 0 1
#hex:    C         2          0          D
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
        print('4- Uh-oh, command returned an error.')
        #raise RuntimeError('4- Uh-oh, command returned an error.')
    return [raw_ch0, raw_ch1, raw_ch2, raw_ch3]

def evm_config(serial_port):
    # Put the EVM into sleep mode
    write_reg(serial_port, EVM_CONFIG, SLEEP_MODE)
    # Write channel configurations
    for k,v in config_multichannel.items():
        write_reg(serial_port, k, v)
    # Put it back into normal operating mode
    write_reg(serial_port, EVM_CONFIG, CONFIG_SETTING)

async def main(websocket, path):
    # Identify EVM by USB VID/PID match
    detected_ports = list(serial.tools.list_ports.grep('2047:08F8'))
    if not detected_ports:
        raise RuntimeError('No EVM found.')
    else:
        # open the serial device.
        evm = serial.Serial(detected_ports[0].device, 115200, timeout=1)

    device_id = read_reg(evm, EVM_DEVICE_ID)
    evm_config(evm)

    h5f = tables.open_file(filename, 'a', title="EVM Logger Data")

    try:
        tbl = h5f.get_node('/logdata')
        print("Appending existing table in: {}".format(filename))
    except tables.NoSuchNodeError:
        table_definition = {
            'time_utc': tables.Time64Col(),
            'data_ch0': tables.UInt32Col(),
            'data_ch1': tables.UInt32Col(),
            'data_ch2': tables.UInt32Col(),
            'data_ch3': tables.UInt32Col()
        }
        tbl = h5f.create_table('/', 'logdata', description=table_definition, title='EVM dataset')
        print("Created new table in: {}".format(filename))


    start_stream(evm)
    print("Beginning logging...")

    # default values:
    min_def = float(' inf')
    max_def = float('-inf')
    max_ = [max_def, max_def, max_def, max_def]
    min_ = [min_def, min_def, min_def, min_def]
    ch_num = 4

    ms = time.time()*1000.0

    while True:
        try:
            raw_ = read_stream(evm) # get array of 4 measurements
            socket_buff = ""

            for i in range(ch_num):
                tbl.row['time_utc'] = time.time()

                if raw_[i] and not (raw_[i] & 0xF0000000):
                    tbl.row['data_ch'+str(i)] = raw_[i]

                    # adaptive calibration:
                    if raw_[i] > max_[i]: max_[i] = raw_[i]
                    if raw_[i] < min_[i]: min_[i] = raw_[i]

                    # remove calibration offset
                    calibrated = raw_[i] - min_[i]
                    range_ = max_[i] - min_[i]

                    if range_ != 0:
                        percentage = round(100 * calibrated / range_, 1)
                        separator = (',' if (i < ch_num-1) else '')
                        socket_buff += str(percentage) + separator
                        print(str(i) + ' ' + str(percentage) +
                              (3*i+1)*'\t' + int(percentage/8) * 'x')
                    else:
                        print('Calib needed:\t', min_[i],
                                           '\t', raw_[i],
                                           '\t', max_[i],
                                           '\t', calibrated,
                                           '\t', range_)
                        socket_buff = ""
                        break
                tbl.row.append()
                tbl.flush()

            await websocket.send(socket_buff)
            print('time dif: ' + str(round(time.time()*1000.0 - ms, 2)) + '\n')
            ms = time.time()*1000.0

        except Exception as e:
            print('\n  !!! Exception:')
            print(e)
            break

    # If we handled errors like KeyboardInterrupt properly, we'd get here:
    print("Cleaning up...")
    tbl.close()
    h5f.close()

if __name__ == '__main__':
    start_server = websockets.serve(main, host, port)
    asyncio.get_event_loop().run_until_complete(start_server)
    print('Server running: start the listener and calibrate your sensor!')
    asyncio.get_event_loop().run_forever()

