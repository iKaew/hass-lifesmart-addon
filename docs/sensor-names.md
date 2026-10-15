# Sensor channel names

Local hubs can return default channel names such as `{$EPN} {T}` rather than
human-readable labels. Sensor and binary sensor entities now remove the device
name template and let Home Assistant translate their existing device class.
For example, a device named `Utility sensor` exposes `Utility sensor Temperature`
instead of `Utility sensor {$EPN} {T}`. Battery, humidity, illuminance and moisture
use the same Home Assistant naming mechanism.

Explicit channel names, including `{$EPN} Desk reading`, remain custom names.
An unknown template suffix falls back to the channel ID. A channel without a
device class or a documented functional label also retains its channel ID.
Existing entity IDs and unique IDs remain unchanged; saved entity names in the
Home Assistant registry continue to override integration-provided names.

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
