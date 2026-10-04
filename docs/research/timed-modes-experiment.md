# Timed-modes experiment

**Question:** does a timed-mode countdown exist over BLE?

**Status:** concluded. The result is settled; do not re-run.

**Risk:** none from the experiment itself. Every write was performed by the heater's own panel.

## Why it matters

Whether params 17-19 ever become non-zero decides whether a client can show a countdown. They read `0x0000` everywhere else because the official app's Block 11 read is only 16 words.

## Result

ELECTRIC mode was set to 2 days from the control panel at time T, while a logger held the connection and read Block 11 every 30 seconds.

```text
T         ELECTRIC set on panel, duration=2d   ELECTRIC_DAYS (p19) = 2
T+23h12m  ELECTRIC_DAYS (p19): 2 -> 1   (about)
T+47h12m  ELECTRIC_DAYS (p19): 1 -> 0, mode word flips to 0x0004 (HYBRID)
          in the same read   (about)
```

Three conclusions, all **verified on hardware**:

- **The countdown exists over BLE, at p19** (`ELECTRIC_MODE_REMAINING_DAYS`). `p19` decremented on a fixed daily wall-clock tick about 24h00m01s apart; the first tick came about 23h12m after the set, so the counter is not a timer started at the moment of setting. It reached 0 exactly when the mode reverted.
- **The mode reverts to HYBRID**, the permanent mode active before the timed mode, in the same read where the counter hits 0. This matches the handbook's statement that expiry returns to the prior mode.
- **No early revert in ELECTRIC mode.** The handbook (`2000620230`, line 404) states a revert at "9 hours remaining" for VACATION only. This run was ELECTRIC and reverted exactly at `p19 == 0`. Use "count reaches zero" as the revert signal.

## Vacation counter check

Vacation was set on the panel for 5 days and the heater read over BLE (**verified on hardware**):

- While Vacation was active, the mode word read VACATION with duration 5 and p17 (`VACATION_MODE_REMAINING_DAYS`) read 5. p18 and p19 stayed 0.
- The setpoint parameter kept reading its stored value (124 F) while the panel showed 50 F.
- After switching back to Hybrid on the panel, the mode word read HYBRID with duration 0 on the next reading, but p17 kept reading 5 for more than two minutes. The counter is not cleared by an early cancel, so it is meaningful only while its mode is active.

## Not retested

- **VACATION decrement** (counter p17). The decrement tick has not been observed.
- **GUEST** (counter p18, **unverified**). Mode 3 has never been written by anything observed, in any capture. It stays out of scope.

## Mode write pattern in the captures

Every `0x40` mode write across all five Android captures showed this pattern:

```text
duration = 0  only ever with:  0f 00 04 (HYBRID)      0f 00 05 (HEAT_PUMP)
ELECTRIC always timed:         0f 01 01  0f 02 01  0f 03 01  0f 05 01
VACATION always timed:         0f 02 02  0f 03 02  0f 04 02
GUEST (mode 3):                never written, in any capture
```

So HYBRID and HEAT_PUMP are the only permanent modes, and `duration = 0` is meaningless for modes 1-3. The app has no "cancel": to end a timed mode, select a different mode ([Block 11](../protocol/block-11.md)).
