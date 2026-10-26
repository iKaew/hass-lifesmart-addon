# Battery percentages and missing readings

For the documented `V` battery channels below, `v` is the converted battery
percentage. On the observed water-leak, environmental, door and clicker devices,
`val` is a raw voltage reading;
it is not tenths of a percentage. Dividing `val: 150` by ten therefore produces
an incorrect `15%`. A corresponding `rv: 3.0` does not establish remaining capacity
or a discharge curve.

| Device family | Model IDs with percentage-only `V` handling |
| --- | --- |
| Water leak / environment | `SL_SC_WA`, `SL_SC_BE` |
| Door contacts | `SL_SC_G`, `SL_SC_BG` |
| Motion sensors | `SL_SC_MHW`, `SL_SC_BM`, `SL_SC_CM` |
| CUBE Clicker / free button | `SL_SC_BB`, `SL_SC_BB_V2` |

The door contact observed over TCP reported `val: 137`, `rv: 2.74` with no `v`.
It must remain unknown rather than display `13.7%`; the Station's separate local
percentage interface reported `6%`. No voltage-to-capacity formula is inferred.
The clicker reported `val: 150`, `rv: 3.0`, while that interface returned `100%`.
Motion sensors and the other variants are covered by the protocol documentation
and synthetic tests, not hardware verification. Clicker battery entities are
created only when a `V` channel exists; button events are outside this extension.

The integration accepts a finite numeric `v` between 0 and 100 for these channels.
Missing, null, boolean, nonnumeric, non-finite and out-of-range values become
`None`, which Home Assistant represents as `unknown`. A valid zero stays `0%`.
This applies at initial setup and on subsequent updates, without requiring any
additional service on the Smart Station.

| Input for the battery channel | Result |
| --- | --- |
| `{"val": 150, "rv": 3.0}` | Unknown |
| `{"v": null, "val": 150}` | Unknown |
| `{"v": 100, "val": 150}` | 100% |
| `{"v": 0, "val": 100}` | 0% |

“Unknown” means there is no usable percentage. It is different from `unavailable`,
which indicates that the integration or device is not reachable. Home Assistant
localizes these labels; numeric battery sensors must not return the string `N/A`.
Dashboards can render a different placeholder for `unknown` if desired.

Existing entity IDs, custom names and recorder history are preserved. Historical
values produced by the old conversion remain in the database; an increase after
the fix does not necessarily mean the battery was replaced.

The change is limited to the listed documented model/channel combinations. It does
not remove valid temperature/humidity conversions or assume that every model uses
the same raw battery representation.

## References

- LifeSmart, *Local Interfaces of LifeSmart Smart Station*, 2023-09-26,
  sections 6.3.6–6.3.7 and 6.6.1–6.6.4, printed pages 29–30 and 41–43
  ([vendor document hosted in a community repository](https://github.com/ALITECHLAB/lifesmart_local_addon/blob/c0d4b38121d35bc274f2d800f925f8004b69bcd3/Docs/Local%20Interfaces%20of%20LifeSmart%20Smart%20Station_20230926.pdf)).
- [Home Assistant sensor value requirements](https://contributors.home-assistant.io/core/entities/sensor/#properties).
