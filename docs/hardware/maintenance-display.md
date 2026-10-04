# Maintenance display mode

The control panel can show live sensor values, so a value read off the panel can be searched for in a simultaneous BLE dump, the most direct route to the unnamed Block 11 parameters. The access procedure is **from the handbook** (Service Handbook `2000620230`, "Accessing the Maintenance Display").

## Entering the mode

> Press the Up and Down Temperature buttons at the same time and hold for (3) seconds.

The display alternates between the designation (for example `P1` or `H1`) and its value. Use Up and Down to page. The panel returns to normal after about 15 seconds with no button press.

!!! warning "Do not hold the buttons longer than three seconds"
    The same two buttons held longer show `CLR` and clear the stored error codes. Hold for three seconds, no more.

## Codes

| Code | Meaning | Sensor |
| --- | --- | --- |
| P1 | Upper tank temperature | 50kΩ @ 25C, outer upper tank wall |
| P2 | Lower tank temperature | 50kΩ @ 25C, outer lower tank wall |
| P3 | Coil temperature | 10kΩ @ 25C, evaporator hairpin |
| P4 | Discharge temperature | 50kΩ @ 25C, compressor discharge pipe |
| P5 | Suction temperature | 10kΩ @ 25C, evaporator outlet |
| P6 | Ambient temperature | 10kΩ @ 25C, within the heat pump assembly |
| P7 | EEV pulses | Expansion valve opening |
| P8 | Upper element status | 0 off, 1 on |
| P9 | Lower element status | 0 off, 1 on |
| P10 | Software version | "vXY" means version X.Y |
| H1-H4 | Fault history | Newest first |

The handbook also tabulates both thermistor curves (50kΩ and 10kΩ, 15-50C in 1C steps), useful if a raw ADC or resistance value turns up.

## Panel experiment (not yet run)

1. Enter maintenance display mode and record P1-P6, P8 and P9 with a rough wall-clock time. P8 and P9 are probably what the thermometer LED on the panel reflects, and a boolean that flips is far easier to find in a dump than a temperature.
2. At the same time, dump every block with any read-only block sweep.
3. Search the dump for each value under each plausible encoding (the sensors' encoding is unknown):
    - `degC * 256` (the setpoint encoding)
    - `degC * 10`, `degC * 100`, raw `degC`
    - `degF * 10`, raw `degF`
    - raw ADC counts or thermistor resistance in ohms

Best run right after a large hot water draw, when P1 and P2 differ strongly from each other and from the setpoint.

## What is already known

- Live BLE data is confined to Block 11 params 0-4, 15 and Block 2 param 7. Blocks 21-26 read all zeros on the test unit.
- Block 11 params 1-4 never changed across long runs, including Hybrid with the compressor running, so they may be static configuration ([Block 11](../protocol/block-11.md)).
- The panel is the only known place these sensors are visible.
