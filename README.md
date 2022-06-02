# libboinc-client-py `boinc`

Python API bindings for the XML RPC_GUI API that the BOINC core client exposes.

A separate packaging of the core functionality of MestreLion's [BOINC Monitor](https://github.com/MestreLion/boinc-indicator/). Extraction and Python 3 conversion helped along by drakej's [fork](https://github.com/drakej/boinc-indicator/).


## Overview

Mostly copied from the original project's [README](https://github.com/MestreLion/boinc-indicator/blob/master/README.md).


### The Problem

The XML RPC_GUI protocol also has a few drawbacks:

- The offical API library provided, gui_rpc_client, is C++.
- The command-line utility `boinccmd`, the other high-level interface to boinc client, is easy to use and well documented, but hard and not reliable to use its output to build a GUI manager/monitor on top of it, requiring complex string manipulation and many shell calls.


### The Solution

- Provide the GUI_RPC API in a fully, easily reusable form. Actually, 2 APIs: one for low-level GUI_RPC, and another, higher level similar to `boinccmd` command-line options.
- Everything in Python, to lower the entry barrier and promote third party managers, monitors and GUIs to use a standard library.


### The Approach

- `gui_rpc_client.py` is a re-write of `gui_rpc_client.{h,cpp}` in Python. Should provide the GUI_RPC API as faithfully as possible, in a Pythonic way, similar to what PyGTK/PyGI/PyGObject/gir bindings do with Gtk/GLib/etc libs. It starts as direct copy-and-paste of the C++ code as comments, and is progressively translated to Python code. C++ structs and enums are converted to classes, `class RpcClient()` being the port of `struct RPC_CLIENT`.
- `client.py` is a conversion of `boinccmd`, not only from C++ to Python, but also from a command-line utility to an API library. Uses `gui_rpc_client.RpcClient` calls to provide an interface that closely matches the command-line options of `boinccmd`, ported as methods of a `BoincClient` class.
- Since API and App Indicator are distinct, in the future they they can be packaged separately: API as a library package named `python-boinc-gui-rpc` or similar, installed somewhere in `PYTHONPATH`, while the app indicator monitor can be, for example `boinc-monitor` or `boinc-indicator`. Indicator depends on API and recommends `boinc-manager`, and API depends on `boinc-client`.


## Using the API library

Package and modules names are not set in stone yet. Actually, API is still a non-working stub. But, assuming a `boinc` package in `PYTHONPATH`, it will be something like:

For the client API (emulating the options of `boinccmd`):

	from boinc.client import BoincClient
	bc = BoincClient()
	status = bc.get_cc_status()

For the XML GUI_RPC API:

	from boinc.gui_rpc_client import RpcClient
	rpc = RpcClient()
	rpc.init()
	status = rpc.get_status()

The client API is higher-level and more straightforward than the GUI_RPC, since the client automatically deals with `exchange_version()`, `read_gui_rpc_password()` and `authorize()`. Until the client is expanded, GUI_RPC is more featureful.


## Licenses and Copyright

* Copyright (C) 2013 Rodigo Silva (MestreLion) <linux@rodrigosilva.com>.
* Copyright (C) 2020 drakej <https://github.com/drakej>.
* Copyright (C) 2022 Kevin Whalen (KevinWhalen) <kwhalen2@kent.edu>.

License GPLv3+: GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.

This is free software: you are free to change and redistribute it.

There is NO WARRANTY, to the extent permitted by law.
