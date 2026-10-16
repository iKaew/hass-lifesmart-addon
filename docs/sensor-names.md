# Sensor channel names

Local hubs can return default channel names such as `{$EPN} {T}` rather than
human-readable labels. Sensor and binary sensor entities remove the device-name
template. Only explicitly mapped model/channel pairs use translated functions.
For example, a device named `Utility sensor` exposes `Utility sensor Temperature`
instead of `Utility sensor {$EPN} {T}`. Battery, humidity, illuminance and moisture
use the same Home Assistant naming mechanism.

Explicit channel names, including `{$EPN} Desk reading`, remain custom names.
An unknown template suffix falls back to the channel ID. For models or channels
outside the mapping, default or missing names also retain the channel ID, even
when a device class exists. For example, SL_P and SL_JEMA inputs retain P5/P6/P7
instead of all becoming "Lock"; V_485_P measurements retain EE1/EE2 and
CH2OPPM/NH3PPM instead of losing their channel or gas distinctions.
Existing entity IDs and unique IDs remain unchanged; saved entity names in the
Home Assistant registry continue to override integration-provided names.

The mapping is deliberately limited to the documented channels below. Other
models require an explicit mapping after their channel functions are verified.

| Model | Channels using HA device-class names |
| --- | --- |
| SL_SC_BE | T (Temperature), H (Humidity), Z (Illuminance), V (Battery) |
| SL_SC_WA | WA (Moisture), V (Battery) |

The gas sensor family needs more specific labels than its existing device
classes provide:

| Model | Channel | Default name (English) |
| --- | --- | --- |
| SL_SC_CP | P1 | Gas concentration |
| SL_SC_CH | P1 | Formaldehyde concentration |
| Both | P2 | Alarm threshold |
| Both | P3 | Alarm sound |

P3 indicates whether the sounder is active. It is not the concentration alarm
condition: that condition is reported on P1. This change only affects names;
it does not change readings, units, device classes, alarm logic or commands.

References:

- [Home Assistant entity naming](https://developers.home-assistant.io/docs/core/entity/#entity-naming)
- LifeSmart *Smart Device Specification*, v2.32, sections 2.6.3–2.6.6,
  available from the [official documentation center](https://ilifesmart.com/open/document/developmentGuidance)
  (account sign-in required). These sections document the environmental, water
  flooding, formaldehyde and gas sensor channels.
