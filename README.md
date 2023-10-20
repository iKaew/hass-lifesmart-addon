

Instructions
==== 
Lifesmart devices for Home Assistant

Prerequisites: 
---
1. Find current LifeSmart region for your country (America, Europe, Asia Pacific, China (old, new , VIP)). [See regional server list here](./docs/api-regions.md)


1. New Application from LifeSmart Open Platform to obtain `app key` and `app token`, http://www.ilifesmart.com/open/login (caution! this url is not https and all content is in chinese, browse with translation should help)

1. Login to application created in previous bullet with LifeSmart user to grant 3rd party application access to get `user token`, please ensure you use the api address with correct region. 

**Please note that, by default application from LifeSmart Open Platform won't return you Lock devices type. You have to contact them to get it granted to your application.**

How it works:
---

- This add-on required internet access, first when add-on loaded it will call LifeSmart API to get all devices to setup on Home Assistant, After that it will get updated from LifeSmart via websocket. There is no direct communication between HA and local LifeSmart hub at the moment. 


How to install:
---

### Manual 

1. Copy the custom_components/lifesmart directory to config/custom_components/ of Home Assistant

1. Setup integration via add Integration

   Configuration required for this add-on via UI (see example screen below)
   ```
   lifesmart:
     appkey: | your appkey|  
     apptoken: | your apptoken| 
     usertoken: | your usertoken|  
     userid: | your userid| 
     url: | your api address|  #e.g. api.apz.ilifesmart.com for asia pacific, api.us.ilifesmart.com for US  
    ```


### HACS with Custom repository (Recommended)
1. Go to HACS > Integration > choose Custom Repository

   ![HACS Custom Repository](https://github.com/iKaew/hass-lifesmart-addon/assets/6348112/2499f1f5-f973-40db-8bf5-76b08e3faa1d)
1. In custom repository dialog enter 

   Repository: `https://github.com/iKaew/hass-lifesmart-addon`

   Category: `Integration`

1. Click Add
1. Setup integration via add Integration

Via HACS should allow you to get new version when it ready. 

After the addon stable, I'll push the repo be in deault list of HACS and (long way) later to be included in Official Integration of HA.

Example
---
![Alt text](./docs/example-configuration.png)
![Alt text](./docs/example-image.png)
![Alt text](./docs/example-image-4.png)
![Alt text](./docs/example-image-2.png)
![Alt text](./docs/example-image-3.png)


Supported devices:
---
Since there are a lot of refactored and code changes, some old device removed from supported list for now. 
1. Switch 

1. Intelligent door lock information feedback

1. Smart Plug

1. Dynamic sensor, door sensor, environmental sensor, formaldehyde/gas sensor

1. ~~Lighting: currently only supports Super Bowl night light~~

1. ~~Universal remote control~~

1. ~~Curtain motor (only support Duya motor)~~

1. ~~Air conditioning control panel~~

List of supported devices

Switch: 
| Model  | Remark |
| ------ | ------ |
| OD_WE_OT1 | |
| SL_MC_ND1 | |
| SL_MC_ND2 | |
| SL_MC_ND3 | |
| SL_NATURE | |
| SL_OL | |
| SL_OL_3C | |
| SL_OL_DE | |
| SL_OL_UK | |
| SL_OL_UL | |
| SL_OL_W | |
| SL_P_SW | |
| SL_S | |
| SL_SF_IF1 | |
| SL_SF_IF2 | |
| SL_SF_IF3 | |
| SL_SF_RC | |
| SL_SPWM | |
| SL_SW_CP1 | |
| SL_SW_CP2 | |
| SL_SW_CP3 | |
| SL_SW_DM1 | |
| SL_SW_FE1 | |
| SL_SW_FE2 | |
| SL_SW_IF1 | |
| SL_SW_IF2 | |
| SL_SW_IF3 | |
| SL_SW_MJ1 | Tested with real devices |
| SL_SW_MJ2 | Tested with real devices |
| SL_SW_MJ3 | |
| SL_SW_ND1 | |
| SL_SW_ND2 | |
| SL_SW_ND3 | |
| SL_SW_NS3 | |
| SL_SW_RC | |
| SL_SW_RC1 | |
| SL_SW_RC2 | |
| SL_SW_RC3 | |
| SL_SW_NS1 | |
| SL_SW_NS2 | |
| SL_SW_NS3 | |
| V_IND_S | |

Door Locks: 
| Model  | Remark |
| ------ | ------ |
| SL_LK_LS | Tested with real devices |
| SL_LK_GTM | |
| SL_LK_AG | |
| SL_LK_SG | |
| SL_LK_YL | |

Generic Controller: 
| Model  | Remark |
| ------ | ------ |
| SL_P | Tested with real devices |


Smart Plug: 
| Model  | Remark |
| ------ | ------ |
| SL_OE_DE | Metering supported , Tested with real devices |
| SL_OE_3C | Metering supported |
| SL_OL_W | Metering supported |
| OD_WE_OT1 | |
| ~~SL_OL_UL~~ | |
| ~~SL_OL_UK~~ | |
| ~~SL_OL_THE~~ | |
| ~~SL_OL_3C~~ | |
| ~~SL_O~~L | |


This project is forked/combined from serveral projects below 
---
- https://github.com/skyzhishui/custom_components by @skyzhishui
- https://github.com/Blankdlh/hass-lifesmart by @Blankdlh
- https://github.com/likso/hass-lifesmart by @likso
