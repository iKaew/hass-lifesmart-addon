# Optional OpenDev battery readings

This option supplies battery percentages for the documented local battery channels
listed below when TCP does not include `V.v`.
It reads the Smart Station's converted percentage over UDP; it does not estimate
capacity from voltage. The existing battery entities keep their IDs, while other
channels and controls continue to use the TCP connection.

OpenDev is optional and disabled by default. The [missing-value fix](battery-values.md)
works without OpenDev. Installing or upgrading the integration does not enable
any service on the Station.

| Device family | Supported model IDs | Verification |
| --- | --- | --- |
| Water leak / environment | `SL_SC_WA`, `SL_SC_BE` | Hardware reads and synthetic tests |
| Door contacts | `SL_SC_G`, `SL_SC_BG` | `SL_SC_BG` hardware reads; both models tested synthetically |
| Motion sensors | `SL_SC_MHW`, `SL_SC_BM`, `SL_SC_CM` | Protocol documentation and synthetic tests only |
| CUBE Clicker / free button | `SL_SC_BB`, `SL_SC_BB_V2` | `SL_SC_BB` hardware reads; both models tested synthetically |

Only a reported `V` channel gets a battery entity. Clickers now receive a battery
entity even with OpenDev disabled (valid TCP `v`, otherwise unknown); this does
not add button-event or automation-trigger support. Other battery-powered models
are not automatically included: their channel semantics must first be checked.
If battery percentages are not needed, leave the option disabled. To obtain a
missing percentage on a compatible Station, follow the setup below and restart
the Station after activation. No extra activation is needed per sensor once
the Station service is running. After adding devices, reload the LifeSmart entry
to refresh its device list; OpenDev polling alone does not discover HA entities.

## Configure the Station first

The supported setup is LifeSmart's **QR-code activation** mode. Its local-interface
document distinguishes this from smart-template activation: QR mode permits an
ephemeral client UDP port, whereas template mode describes a fixed port and discovery
exchange. This client implements QR mode, not the template discovery handshake.

1. Obtain a compatible activation profile from LifeSmart or your solution provider.
   Its OpenDev model, token and activation key (`encrypt`) form a matching profile.
   The model is an access identifier, not the Station's hardware model. These
   values are separate from TCP passwords and cloud API credentials.
2. In the LifeSmart app, scan the provider's activation QR code, select the intended
   Station, inspect the proposed configuration and confirm it. Restart that Station
   if required by the activation instructions; this briefly interrupts its services.
3. Confirm the configured OpenDev service appears in the app's device list after
   restart. Merely finding or saving an OpenDev template is not proof of a working
   interface. Do not enable both activation methods for this setup.
4. Ensure the HA host can reach that Station on UDP 12348 and receive replies to its
   ephemeral source port. An already working TCP 8888 connection does not prove that
   this separate UDP service is enabled or reachable.

A provider may supply an existing profile, so every end user does not necessarily
need to register a new one personally. Arbitrary model/token strings are not a
substitute for a provisioned profile. The [ALITECH project's activation guide](https://github.com/ALITECHLAB/lifesmart_local_addon/blob/c0d4b38121d35bc274f2d800f925f8004b69bcd3/Docs/readme.md)
is a community example whose QR profile was used for hardware validation. This
integration does not embed its shared credentials or claim compatibility with all
Station firmware. Its activation key belongs to Station setup; HA's signed read
requests use the model and token, with no encrypted-payload mode implemented.

## Configure Home Assistant

1. Keep the existing local LifeSmart TCP entry configured and loaded.
2. Open **Settings → Devices & services → LifeSmart → Configure → OpenDev battery percentages**.
3. Enable battery queries and enter the matching OpenDev **model** and **token**.
   The Station address comes from the existing local entry.
4. Submit. The options flow performs a read-only query before saving and reloads the
   entry. Failed validation leaves the existing options unchanged. Tokens are
   masked in the form and redacted in diagnostics.

The new options are available in local mode only. There is no need to configure a
cloud account or replace an existing HomeKit pairing. To stop polling, turn off the
OpenDev option. This does not remove the service previously enabled on the Station;
manage that separately in the LifeSmart app or with the profile provider.

## Reading behavior and troubleshooting

A shared coordinator requests the device list every five minutes, with a six-second
timeout. Only matching, online devices with valid `V.v` percentages are used.
TCP battery updates cannot overwrite the selected OpenDev source. No control,
event-subscription or Station-configuration requests are sent by this client.

| Situation | Battery state |
| --- | --- |
| OpenDev disabled; TCP has a valid percentage | TCP percentage |
| OpenDev disabled; TCP has no valid percentage | Unknown |
| OpenDev enabled; a matching device has valid `V.v` | OpenDev percentage |
| Query fails, device is offline/missing, or percentage is invalid | Unavailable |
| A subsequent query succeeds | Percentage recovers automatically |

For a failed setup, check the selected Station, activation method, matching profile,
restart completion and UDP reachability. A timeout alone does not identify which
of these is wrong. Other TCP entities can continue working during an OpenDev failure.

`state_source: opendev` identifies the battery source. `battery_last_reported`
preserves the Station's original `V.valts`; it may be days older than the query.
Diagnostics separately expose `last_successful_query` and `last_update_success`.
Polling does not wake a battery device or measure its remaining capacity directly.

Hardware validation used one Station with discovery firmware `1.0.93p71` and
`MGAFWVER=3366`. The water-leak/environment sensors returned 100%, matching the app,
while TCP alone had produced incorrect readings near 15%. Subsequent read-only
queries found a door contact (`SL_SC_BG`) with TCP `val: 137`, `rv: 2.74`, no `v`,
and OpenDev `v: 6`; a clicker (`SL_SC_BB`) had TCP `val: 150`, `rv: 3.0`, no `v`,
and OpenDev `v: 100`. These are Station-reported percentages, not independent
capacity measurements. The door/clicker extension has not been deployed to HA
for hardware validation. Motion sensors and other variants have not been queried
on hardware. This is not a compatibility guarantee for other firmware, template
mode or encrypted variants.

For HACS installations, a branch or PR alone does not change the release being
downloaded. Use a release containing this change when available; updating to a
release without it can overwrite a local patch.

## Protocol reference

LifeSmart, *Local Interfaces of LifeSmart Smart Station*, 2023-09-26: sections
1.1–1.2 (activation), 3 (signed request/response protocol), 6.3.6–6.3.7 and 6.6.1–6.6.4 (battery
fields). See the [vendor PDF hosted by ALITECH](https://github.com/ALITECHLAB/lifesmart_local_addon/blob/c0d4b38121d35bc274f2d800f925f8004b69bcd3/Docs/Local%20Interfaces%20of%20LifeSmart%20Smart%20Station_20230926.pdf).
