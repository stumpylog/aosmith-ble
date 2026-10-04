# Operating limits

Heater limits, useful as validation bounds for anything that writes. Every item is **from the handbook** (Service Handbook `2000620230`) unless marked.

| Item | Limit |
| --- | --- |
| Setpoint | 95-150°F (35-65.6°C). Factory default 120°F. |
| Vacation | Fixed 50°F setpoint on the panel (the BLE setpoint parameter keeps its stored value), 1-99 days or permanently on, default 7. |
| Electric | 1-7 days, default 3. Holding the Electric button for 5 s unlocks 1-99 days or permanent. |
| Guest | 1-7 days, default 3. |
| Hot Water+ | An overlay on Hybrid, Heat Pump or Electric adding +10/+20/+30°F. It is a separate field, not a sixth mode value. |
| Heat pump window | Ambient 37-120°F. The heat pump is also inhibited below 59°F tank temperature. |
| Non-error display states | `HPO` (outside heat pump range), `ICE` (defrost), `CLR`, `ON`. |

## Timed-mode revert

The handbook (`2000620230`, line 404) says Vacation mode reverts when 9 hours remain. Hardware testing used Electric mode and saw no early revert, so the Vacation figure is unconfirmed; see [timed-modes experiment](../research/timed-modes-experiment.md). Treat "the count reaches zero" as the revert signal.

## Panel display

A blinking timer means the setting is unconfirmed and awaiting the Mode or Enter press. A display alternating between the setpoint and the remaining days is the normal cycle for an active timed mode (**from the handbook**).
