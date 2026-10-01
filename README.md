# Home Assistant Integration for Waterkotte Heatpumps [+2020]

![logo](https://github.com/marq24/ha-waterkotte/raw/main/logo.png)

This Home Assistant Integration is providing information from the German heatpump pioneer Waterkotte. In addition and where possible functions are provided to control the system.

__Please note__, _that this integration is not official and not supported by the Waterkotte development team. I am not affiliated with Waterkotte in any way._

All data will be fetched (or send) to your Waterkotte via the build in webserver of the unit. So the functionality is based on the data and settings that are available also via the frontend that you can directly access via a web-browser.

[![hacs_badge][hacsbadge]][hacs] [![hainstall][hainstallbadge]][hainstall] [![Wero][werobadge]][wero] [![wise][wisebadge]][wise] [![Revolut][revolutbadge]][revolut] [![PayPal][paypalbadge]][paypal] [![github][ghsbadge]][ghs] [![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

## This component will set up the following platforms

| Platform        | Description                                          |
|-----------------|------------------------------------------------------|
| `binary_sensor` | Show something `True` or `False`.                    |
| `sensor`        | Show info from Waterkotte Heatpump API.              |
| `switch`        | Switch something `True` or `False`.                  |
| `select`        | Select a value from options.                         |
| `number`        | adjustable Temperatures (demanded or heating curves) |
| `datetime`      | Start and end of the holiday                         |
| `time`          | Start time of the water disinfection                 |
| `service`       | Provides services to interact with heatpump          |

## Disclaimer

Please be aware, that we are developing this integration to best of our knowledge and belief, but cant give a guarantee. Therefore, use this integration **at your own risk**.

## What you can get [with Version 2024.3.0 (or higher)]

[![sampleview](https://github.com/marq24/ha-waterkotte/raw/main/sample-view-s.png)](https://github.com/marq24/ha-waterkotte/raw/main/sample-view.png)

[[Get the sources for the sample dashboard_above](https://github.com/marq24/ha-waterkotte/blob/main/sample-view.yaml)] - Please note, that this sample dashboard makes use of the custom [multiple-entity-row](https://github.com/benct/lovelace-multiple-entity-row) frontend integration that need to be installed separately. 

## Setup / Installation
if you have installed the previous version of the waterkotte integration from me (marq24) - please [follow the migration guide](https://github.com/marq24/ha-waterkotte/blob/main/README.md#migration).

### Step I: Install the integration

#### Option 1: via HACS
[![Open your Home Assistant instance and adding repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marq24&repository=ha-waterkotte&category=integration)

- Install [Home Assistant Community Store (HACS)](https://hacs.xyz/)
- Add integration repository (search for "Waterkotte Heatpump [+2020]" in "Explore & Download Repositories")
- Use the 3-dots at the right of the list entry (not at the top bar!) to download/install the custom integration - the latest release version is automatically selected. Only select a different version if you have specific reasons.
- After you presses download and the process has completed, you must __Restart Home Assistant__ to install all dependencies
- Setup the custom integration as described below (see _Step II: Adding or enabling the integration_)

#### Option 2: manual steps

- Copy all files from `custom_components/waterkotte_heatpump/` to `custom_components/waterkotte_heatpump/` inside your config Home Assistant directory.
- Restart Home Assistant to install all dependencies

### Step II: Adding or enabling the integration

__You must have installed the integration (manually or via HACS before)!__

#### Option 1: My Home Assistant (2021.3+)

Just click the following Button to start the configuration automatically (for the rest see _Option 2: Manually steps by step_):

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=waterkotte_heatpump)

#### Option 2: Manually steps by step

Use the following steps for a manual configuration by adding the custom integration using the web interface and follow instruction on screen:

- Go to `Configuration -> Integrations` and add "Waterkotte" integration
- Provide the IP address (or hostname) of your Waterkotte Heatpump web server
- Select the Interface-Type of your Waterkotte (see table below)
- Select the number of TAGs that can be fetched in a single call to your device (older devices might need to adjust this value - for my in 2022 installed Waterkotte 75 is totally fine)
- Provide area where the heatpump is located

#### General additional notes

After the integration was added you can use the 'config' button to adjust your settings and you can additionally modify the update intervall

If the IP address (or hostname) or the login credentials of your Waterkotte have changed, use the 'Reconfigure' option of the integration entry - there is no need to remove and add the integration again.

Please note, that most of the available sensors are __not__ enabled by default.

#### Entity IDs & multiple Waterkotte heat pumps

The entity IDs are generated by Home Assistant from the device name and the (English) entity name - e.g. `sensor.waterkotte_outdoor_temperature` or `number.waterkotte_t_heating_limit_mixer_1`.

You can add multiple Waterkotte heat pumps to your Home Assistant installation. Each heat pump is identified by its serial number (so the same heat pump can't be added twice). When you add a second heat pump, its device is named `Waterkotte <serial number>` - so its entity IDs look like `sensor.waterkotte_we15123456_outdoor_temperature`.

If you prefer other entity IDs, rename the device (`Settings -> Devices & services -> Devices`) - Home Assistant will then offer to rename the entity IDs of all entities of the device as well.

#### EcoTouch or EasyCon Mode - How to decide?

Please take a look at the different login options and compare with your waterkotte in order to decide, what mode you must select for the integration (sorry only german example screens here)

| EcoTouch | EasyCon                                                                                    |
| --- |--------------------------------------------------------------------------------------------|
| web login form | browser basic-auth                                                                         |
| <img src="https://github.com/marq24/ha-waterkotte/raw/main/login_ecotouch.png" width="350"> | <img src="https://github.com/marq24/ha-waterkotte/raw/main/login_easycon.png" width="350"> |

__Don't get confused!__ The EcoTouch web login for newer Waterkotte models shows the text _EasyCon_ - but when there is a webpage where you must enter the login credentials, then you __must select the EcoTouch__ Mode for this integration!

## Services

The Integration provides currently 4 services. When more than one heat pump is configured, select the heat pump with the `config_entry_id` parameter (optional for a single heat pump).

### Setting dates & times

The start and the end of the holiday (`datetime` entities) and the start time of the water disinfection (`time` entity) can be changed directly on the device page, in dashboards and with the standard actions (`datetime.set_value` / `time.set_value`). The following services are still available (e.g. for existing automations).

#### SET_HOLIDAY
To set the times for the holiday mode use the provided service `waterkotte_heatpump.set_holiday` and set `start` and `end` parameter.

#### SET_DISINFECTION_START_TIME
To set the water disinfection start time (HH:MM) use the provided service `waterkotte_heatpump.set_disinfection_start_time` and set `starthhmm` parameter (seconds will be ignored).

### Get Energy Balance

#### GET_ENERGY_BALANCE
Retrieves the overall energy consumption data for the year

#### GET_ENERGY_BALANCE_MONTHLY
Retrieves the monthly breakdown energy consumption data for a moving 12 month window. 1 = January, 2 = February, etc...

<a href="migration"></a>

## Migration Guide

### Entity IDs of existing installations

Older versions of this integration used fixed entity IDs (`sensor.wkh_temperature_outside` or `sensor.wkh_<serial>_temperature_outside` for multiple heat pumps). The entity IDs of an existing installation are __not__ changed by an update - only entities that are added later get the new entity IDs generated by Home Assistant. The [sample dashboard](https://github.com/marq24/ha-waterkotte/blob/main/sample-view.yaml) uses the entity IDs of a new installation.

If you want to switch to the new entity IDs, rename the device and let Home Assistant rename the entity IDs - please be aware that you then have to adjust your dashboards and automations.

Please note: After the update, older versions of the integration can't be used anymore with your existing configuration (the configuration is migrated) - so please make a backup before updating.

### Removed schedule entities & service

The optional schedule entities (650+) and the 'Set a Schedule' service have been removed. When you update, the schedule entities are removed automatically from your Home Assistant installation (incl. the disabled ones). The schedules can still be adjusted via the web interface of your Waterkotte. The water disinfection schedule is not affected.

### Holiday & BIOS time sensors

The holiday start/end time can be changed with the new `datetime` entities - the holiday sensors are not enabled anymore for new installations (existing installations keep them). The sensors for the holiday start/end time and the BIOS time are timestamp sensors now: their state is an ISO 8601 timestamp (e.g. `2026-12-20T07:00:00+00:00`) instead of the former local text format `2026-12-20 08:00`. Templates or automations that parse the old format need to be adjusted.

### Unavailable entities

An entity is unavailable, when its value could not be read from the heat pump in the last update (before, the entity kept showing the last value it had read).

### Wrong credentials

When the login to the heat pump fails because of wrong credentials, Home Assistant asks you to re-enter the username and password (`Settings -> Devices & services`) instead of retrying forever.

The username and password are changed via 'Reconfigure' now (the options contain only the polling interval and the number of tags per request) - credentials that have been changed via the options of an older version are taken over automatically.

### Migrate from the previous 'ha-waterkotte' repository

This is the new version of the previous 'ha-waterkotte' repository (which have now been renamed to [`ha-waterkotte-the-fork`](https://github.com/marq24/ha-waterkotte-the-fork)). After the refactoring process have been completed, I have decided to create an independent repository - since the refactored version does not have much in common with the origin sources.

Unfortunately HACS does not 'like' renaming of repositories, so you have to perform few steps in order to upgrade your home assistant installation to the latest ha-waterkotte integration version - sorry for this inconvenience!

#### How to migrate to the new integration version
1. make a backup (just in case)
2. go to HACS menu of your home assistant installation
3. remove the (old) custom HACS repository 'https://github.com/marq24/ha-waterkotte'

   (This step will/should remove the Waterkotte Integration entry from the list of installed HACS Integrations)
5. add the __new__ repository 'https://github.com/marq24/ha-waterkotte' to HACS
6. install the waterkotte integration to your local HACS
7. restart your home assistant system

YES - this procedure sounds *totally* silly - but HACS stores a custom-id for each repository - And since I have decided to rename the old repository which base on the work from pattisonmichael to 'https://github.com/marq24/ha-waterkotte-the-fork' and created an independent repository, this procedure is necessary in order to be notified about any future updates.

## Troubleshooting

### Sessions

The Heatpump only allows 2 sessions and there is no way to close a session. Sometimes you will get an error about the login. Just wait a few minutes and it should autocorrect itself. Session usually time out within about 5 min.

### Stale Data

The Heatpump will not always respond with data. This happens usually after the system changes status, e.g. start/stop the heating. There is not much we can do about this, unfortunately. I try to cache the data in possible for a better UX.

## Credits & Kudos

| who                                                    | what                                                                                                                                                                                                                                                                                                                   |
|--------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [@pattisonmichael](https://github.com/pattisonmichael) | This project was initially forked from [Waterkotte-Integration](https://github.com/pattisonmichael/waterkotte-integration) by pattisonmichael  (but both projects drifted apart over time - so this repo is now independent).                                                                                          |
| [@chboland](https://github.com/chboland)               | Christian Boland created a Python Waterkotte library [https://github.com/chboland/pywaterkotte](https://github.com/chboland/pywaterkotte) which was forked by [@pattisonmichael pywatterkotte library](https://github.com/pattisonmichael/pywaterkotte), so this integration is also based on the work from @chboland. |
| [@oncleben31](https://github.com/oncleben31)           | The forked original project was generated via the [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.                                                                                                                                  |
| [@Ludeeus](https://github.com/ludeeus)                 | The forked original code template was mainly taken from the [integration_blueprint](https://github.com/custom-components/integration_blueprint) template                                                                                                                                                               |

---

###### Advertisement / Werbung - alternative way to support me

### Switch to Tibber!

Be smart switch to Tibber - that's what I did in october 2023. If you want to join Tibber (become a customer), you might want to use my personal invitation link. When you use this link, Tibber will grant you and me a bonus of 50,-€ for each of us. This bonus then can be used in the Tibber store (not for your power bill) - e.g. to buy a Tibber Bridge. If you are already a Tibber customer and have not used an invitation link yet, you can also enter one afterward in the Tibber App (up to 14 days). [[see official Tibber support article](https://support.tibber.com/en/articles/4601431-tibber-referral-bonus#h_ae8df266c0)]

Please consider [using my personal Tibber invitation link to join Tibber today](https://invite.tibber.com/6o0kqvzf) or Enter the following code: 6o0kqvzf (six, oscar, zero, kilo, quebec, victor, zulu, foxtrot) afterward in the Tibber App - TIA!

---

[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Default-blue?style=for-the-badge&logo=homeassistantcommunitystore&logoColor=ccc

[hainstall]: https://my.home-assistant.io/redirect/config_flow_start/?domain=waterkotte_heatpump
[hainstallbadge]: https://img.shields.io/badge/dynamic/json?style=for-the-badge&logo=home-assistant&logoColor=ccc&label=usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.waterkotte_heatpump.total

[ghs]: https://github.com/sponsors/marq24
[ghsbadge]: https://img.shields.io/github/sponsors/marq24?style=for-the-badge&logo=github&logoColor=ccc&link=https%3A%2F%2Fgithub.com%2Fsponsors%2Fmarq24&label=Sponsors

[buymecoffee]: https://www.buymeacoffee.com/marquardt24
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a-coffee-blue.svg?style=for-the-badge&logo=buymeacoffee&logoColor=ccc&link=https%3A%2F%2Fwww.buymeacoffee.com%2Fmarquardt24

[buymecoffee2]: https://buymeacoffee.com/marquardt24/membership
[buymecoffeebadge2]: https://img.shields.io/badge/coffee-subs-blue.svg?style=for-the-badge&logo=buymeacoffee&logoColor=ccc&link=https%3A%2F%2Fbuymeacoffee.com%2Fmarquardt24%2Fmembership

[paypal]: https://paypal.me/marq24
[paypalbadge]: https://img.shields.io/badge/paypal-me-blue.svg?style=for-the-badge&logo=paypal&logoColor=ccc&link=https%3A%2F%2Fpaypal.me%2Fmarq24

[wero]: https://share.weropay.eu/p/1/c/6O371wjUW5
[werobadge]: https://img.shields.io/badge/_wero-me_-blue.svg?style=for-the-badge&logo=data:image/svg%2bxml;base64,PHN2ZwogICByb2xlPSJpbWciCiAgIHZpZXdCb3g9IjAgMCA0Mi4wNDY1MDEgNDAuODg2NyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgo+CiAgPGcKICAgICBjbGlwLXBhdGg9InVybCgjY2xpcDApIgogICAgIHRyYW5zZm9ybT0idHJhbnNsYXRlKC01Ny4zODE4KSI+CiAgICA8cGF0aAogICAgICAgZD0ibSA3OC40MDUxLDMwLjM1NzQgYyAwLDAgLTAuMDE4NSwwIC0wLjAyNzgsMCAtNC4zMTg0LDAgLTcuMzQ2MiwtMi41NzY5IC04LjY0NjEsLTUuOTg4NyBIIDk5LjA2OTggQyA5OS4zMDU3LDIzLjA4NDkgOTkuNDI4MywyMS43NzExIDk5LjQyODMsMjAuNDQxIDk5LjQyODMsOS43NTY3MyA5MS43Mzc1LDAuMDEzODc4NyA3OC40MDUxLDAgdiAxMC41MjcgYyA0LjM0MzksMC4wMTE2IDcuMzQxNiwyLjU4MzcgOC42Mjc2LDUuOTg4NyBoIC0yOS4yOTcgYyAtMC4yMzM2LDEuMjgzNyAtMC4zNTM5LDIuNTk3NiAtMC4zNTM5LDMuOTI3NiAwLDEwLjY5MTMgNy43MDAyLDIwLjQ0MzQgMjAuOTk1NSwyMC40NDM0IDAuMDA5MywwIDAuMDE4NSwwIDAuMDI3OCwwIHYgLTEwLjUyNyB6IgogICAgICAgZmlsbD0iI0NDQ0NDQyIvPgogICAgPHBhdGgKICAgICAgIGQ9Im0gNzguMzc3NCw0MC44ODQ0IGMgMC40NTEsMCAwLjg5NTEsLTAuMDEzOSAxLjMzNDYsLTAuMDM0NyAyLjcwMTcsLTAuMTM2NSA1LjE1MzUsLTAuNjgwMSA3LjMzOTMsLTEuNTU2NyAyLjE4NTgsLTAuODc2NyA0LjEwNTcsLTIuMDgxOCA1LjczODcsLTMuNTM5MSAxLjYzMywtMS40NTczIDIuOTgxNSwtMy4xNjQzIDQuMDI3LC01LjA0NDkgMC45NTA2LC0xLjcwOTQgMS42NDQ1LC0zLjU1OTkgMi4wNzk0LC01LjQ5MTMgSCA4Ni42NzIgYyAtMC4yNDk4LDAuNTE1OCAtMC41NDEzLDEuMDA4NSAtMC44NzQ0LDEuNDY4OCAtMC40NTU2LDAuNjI5MSAtMC45ODk5LDEuMjAwNSAtMS41OTYsMS42OTMyIC0wLjYwNiwwLjQ5MjcgLTEuMjg2LDAuOTA5IC0yLjAzNTQsMS4yMzA2IC0wLjc0OTUsMC4zMjE1IC0xLjU2NiwwLjU0ODIgLTIuNDQ5NSwwLjY2MTUgLTAuNDMwMywwLjA1NTUgLTAuODc0NCwwLjA4NzkgLTEuMzM0NywwLjA4NzkgLTIuNzUwMiwwIC00Ljk3NzYsLTEuMDQ3OCAtNi41NjY3LC0yLjY4NzggbCAtNy45NDc2LDcuOTQ3OCBjIDMuNTM2NiwzLjIyOTIgOC40NDI2LDUuMjY0NyAxNC41MTY2LDUuMjY0NyB6IgogICAgICAgZmlsbD0idXJsKCNwYWludDApIgogICAgICAgc3R5bGU9ImZpbGw6dXJsKCNwYWludDApIiAvPgogICAgPHBhdGgKICAgICAgIGQ9Ik0gNzguMzc3NywwIEMgNjcuMTAxNiwwIDU5Ljg1MDIsNy4wMTMzNyA1Ny45MDcyLDE1LjY2OTEgSCA3MC4wOTcgYyAxLjQ1NzIsLTIuOTgxNyA0LjMyNzcsLTUuMTQyMSA4LjI4MDcsLTUuMTQyMSAzLjE1MDMsMCA1LjU5NTIsMS4zNDYyIDcuMTkzNSwzLjM4MTggTCA5My41OTA1LDUuODg5MiBDIDkwLjAwNzYsMi4zMDE1NSA4NC44NTY1LDAuMDAyMzEzMTIgNzguMzc1MywwLjAwMjMxMzEyIFoiCiAgICAgICBmaWxsPSJ1cmwoI3BhaW50MSkiCiAgICAgICBzdHlsZT0iZmlsbDp1cmwoI3BhaW50MSkiIC8+CiAgPC9nPgogIDxkZWZzPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpZD0icGFpbnQwIgogICAgICAgeDE9IjkyLjc0MzY5OCIKICAgICAgIHkxPSIxOC4wMjYxOTkiCiAgICAgICB4Mj0iNzQuNzU0NTAxIgogICAgICAgeTI9IjQwLjMxMDIiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+CiAgICAgIDxzdG9wCiAgICAgICAgIG9mZnNldD0iMC4wMiIKICAgICAgICAgc3RvcC1jb2xvcj0iI0NDQ0NDQyIKICAgICAgICAgc3RvcC1vcGFjaXR5PSIwIi8+CiAgICAgIDxzdG9wCiAgICAgICAgIG9mZnNldD0iMC4zOSIKICAgICAgICAgc3RvcC1jb2xvcj0iI0NDQ0NDQyIKICAgICAgICAgc3RvcC1vcGFjaXR5PSIwLjY2Ii8+CiAgICAgIDxzdG9wCiAgICAgICAgIG9mZnNldD0iMC42OCIKICAgICAgICAgc3RvcC1jb2xvcj0iI0NDQ0NDQyIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaWQ9InBhaW50MSIKICAgICAgIHgxPSI2MS4yNzA0MDEiCiAgICAgICB5MT0iMjMuMDE3Nzk5IgogICAgICAgeDI9Ijc5Ljc1NDUwMSIKICAgICAgIHkyPSI0LjUzNDI5OTkiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+CiAgICAgIDxzdG9wCiAgICAgICAgIG9mZnNldD0iMC4wMiIKICAgICAgICAgc3RvcC1jb2xvcj0iI0NDQ0NDQyIKICAgICAgICAgc3RvcC1vcGFjaXR5PSIwIi8+CiAgICAgIDxzdG9wCiAgICAgICAgIG9mZnNldD0iMC4zOSIKICAgICAgICAgc3RvcC1jb2xvcj0iI0NDQ0NDQyIKICAgICAgICAgc3RvcC1vcGFjaXR5PSIwLjY2Ii8+CiAgICAgIDxzdG9wCiAgICAgICAgIG9mZnNldD0iMC42OCIKICAgICAgICAgc3RvcC1jb2xvcj0iI0NDQ0NDQyIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxjbGlwUGF0aAogICAgICAgaWQ9ImNsaXAwIj4KICAgICAgPHJlY3QKICAgICAgICAgd2lkdGg9IjE3Ny45MSIKICAgICAgICAgaGVpZ2h0PSI0MSIKICAgICAgICAgZmlsbD0iI2ZmZmZmZiIKICAgICAgICAgeD0iMCIKICAgICAgICAgeT0iMCIgLz4KICAgIDwvY2xpcFBhdGg+CiAgPC9kZWZzPgo8L3N2Zz4=

[revolut]: https://revolut.me/marq24
[revolutbadge]: https://img.shields.io/badge/_revolut-me_-blue.svg?style=for-the-badge&logo=revolut&logoColor=ccc&link=https%3A%2F%2Frevolut.me%2Fmarq24

[wise]: https://wise.com/pay/me/matthiasm1046
[wisebadge]: https://img.shields.io/badge/_wise-me_-blue.svg?style=for-the-badge&logo=wise&logoColor=ccc&link=https%3A%2F%2Fwise.com%2Fpay%2Fme%2Fmatthiasm1046