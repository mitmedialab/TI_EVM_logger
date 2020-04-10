# TI_EVM_logger


## What?

This repo holds Python code to stream or log data from evaluation modules made by Texas Instrument.

It works with the following EVM boards:

- Capacitance to digital converters:
    - tested: FDC2214 EVM: https://www.ti.com/tool/FDC2214EVM
    - not tested: FDC2112, FDC2114, and FDC2212 EVMs (+ probably more)

- Inductance to digital converters:
    - LDC1614 EVM: https://www.ti.com/tool/LDC1614EVM
    - not tested: LDC1612, LDC1312, and LDC1314, EVMs (+ probably more)


## How?

Just execute the python script:

    ./evm_logger.py

Note: you might need to tune some of register parameters for your own application, see `config_multichannel` and your favorite datasheet...


## Sources

- Protocol and code example by TI:

    https://e2e.ti.com/support/sensors/f/1023/t/295036#Q40

- 1st implementation:

    https://github.com/2n3906/ldc1614evm_logger

