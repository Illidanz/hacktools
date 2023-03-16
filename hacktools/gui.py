import asyncio
import json
import logging
import os
import re
import threading
import shlex
import sys
import tkinter
import customtkinter
from tqdm import tqdm
from hacktools import common


class tqdm_gui(tqdm):
    def __init__(self, *args, **kwargs):
        super(tqdm_gui, self).__init__(*args, **kwargs)
        logging.info("prg-start-" + str(self.total))

    def display(self, *args, **kwargs):
        d = self.format_dict
        d["bar_format"] = (d["bar_format"] or "{l_bar}<bar/>{r_bar}").replace("{bar}", "<bar/>")
        msg = self.format_meter(**d)
        if "<bar/>" in msg:
            msg = "".join(re.split(r'\|?<bar/>\|?', msg, 1))
        logging.info("prg-update-" + str(self.n) + "-" + msg)
        if sys.stdout is not None:
            super(tqdm_gui, self).display(*args, **kwargs)
    
    def close(self):
        if self.disable:
            return
        logging.info("prg-end")
        if sys.stdout is not None:
            super(tqdm_gui, self).close()
        else:
            self.disable = True
            with self.get_lock():
                self._instances.remove(self)

    def clear(self, *args, **kwargs):
        if sys.stdout is not None:
            super(tqdm_gui, self).clear(*args, **kwargs)

    def cancel(self):
        if self._cancel_callback is not None:
            self._cancel_callback()
        self.close()

    def reset(self, total=None):
        logging.info("prg-start-" + str(total))
        super(tqdm_gui, self).reset(total=total)


class LogHandler(logging.Handler):
    def __init__(self, guiapp):
        logging.Handler.__init__(self)
        self.guiapp = guiapp
        self.prgtotal = 1

    def emit(self, record):
        if record.levelno < logging.INFO:
            return
        # Intercept prg- logs
        msg = self.format(record)
        if msg.startswith("prg-update"):
            split = msg.split("-", 3)
            self.guiapp.progresslabel.configure(text=split[3])
            self.guiapp.progressbar.set(int(split[2]) / self.prgtotal)
            return
        elif msg.startswith("prg-start"):
            self.prgtotal = max(1, int(msg.split("-")[2]))
            self.guiapp.progresslabel.configure(text="")
            self.guiapp.progressbar.set(0)
            return
        elif msg.startswith("prg-end"):
            self.guiapp.progresslabel.configure(text="")
            self.guiapp.progressbar.set(0)
            return
        self.guiapp.addMessages([msg])


class GUIOptions:
    def __init__(self, advanced=False, appearance="System", command="extract", options=[]):
        self.advanced = advanced
        self.appearance = appearance
        self.command = command
        self.options = options


class GUIApp(customtkinter.CTk):
    def __new__(cls):
        if not hasattr(cls, "instance"):
            cls.instance = super(GUIApp, cls).__new__(cls)
        return cls.instance

    def initialize(self, cligroup, appname, appversion, datafolder):
        self.cligroup = cligroup
        self.appname = appname
        self.datafolder = datafolder
        self.thread = None
        self.options = GUIOptions()
        self.commandlist = []
        self.checkboxes = []
        for command in cligroup.commands.keys():
            if not cligroup.commands[command].hidden:
                self.commandlist.append(command)
        # Load config
        self.configdir = os.path.expanduser("~/.hacktools/")
        if not os.path.isdir(self.configdir):
            common.makeFolder(self.configdir)
        if not os.path.isfile(self.configdir + appname + ".json"):
            self.saveOptions()
        else:
            self.loadOptions()
        if self.options.appearance == "Light" or self.options.appearance == "Dark":
            customtkinter.set_appearance_mode(self.options.appearance)

        hacktoolsdir = os.path.dirname(os.path.abspath(__file__))
        icon = os.path.join(hacktoolsdir, "assets", "icon.png")
        if os.path.isfile(icon):
            self.iconphoto(True, tkinter.PhotoImage(file=icon))
            # stop customtkinter from applying its icon even if we're using png
            self._iconbitmap_method_called = True
            if os.name == "nt":
                # On windows, this is needed to show the icon on the taskbar
                try:
                    import ctypes
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("agtt.hacktools.gui.1")
                except:
                    pass
        self.title(appname + " v" + appversion)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.topframe = customtkinter.CTkFrame(self, height=80, corner_radius=0)
        self.topframe.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.topframe.grid_columnconfigure(0, weight=1)
        self.toplabel = customtkinter.CTkLabel(self.topframe, text="Select a command and press Run to execute.")
        self.toplabel.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.advancedlist = ["Toggle Advanced Mode", "Toggle Dark/Light Mode"]
        self.menubutton = customtkinter.CTkOptionMenu(self.topframe, values=self.advancedlist, corner_radius=0, width=28, dynamic_resizing=False, command=self.clickContext)
        self.menubutton.grid(row=0, column=1, padx=10, sticky="e")

        self.commandframe = customtkinter.CTkFrame(self, height=80, corner_radius=0)
        self.commandframe.grid(row=1, column=0, padx=10, sticky="new")
        self.commandframe.grid_columnconfigure(1, weight=1)
        self.commandmenu = customtkinter.CTkOptionMenu(self.commandframe, values=self.commandlist, command=self.changeCommand)
        self.commandmenu.grid(row=1, column=0, padx=10, pady=10)
        self.checkframe = customtkinter.CTkFrame(self.commandframe, height=60, fg_color="transparent")
        self.checkframe.grid(row=1, column=1, pady=10, sticky="nsew")
        self.runbutton = customtkinter.CTkButton(self.commandframe, border_width=2, width=70, text="Run", command=self.runCommand)
        self.runbutton.grid(row=1, column=2, padx=10, pady=10)
        if self.options.command in self.commandlist:
            self.commandmenu.set(self.options.command)
            self.changeCommand(self.options.command)
        else:
            self.changeCommand(self.commandlist[0])

        self.textbox = customtkinter.CTkTextbox(self, width=250)
        self.textbox.grid(row=2, column=0, padx=10, pady=(10, 0), sticky="nsew")
        self.textbox.configure(state=tkinter.DISABLED)

        self.progresslabel = customtkinter.CTkLabel(self, text="")
        self.progresslabel.grid(row=3, column=0, padx=10, sticky="nsew")
        self.progressbar = customtkinter.CTkProgressBar(self)
        self.progressbar.grid(row=4, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.progressbar.set(0)

        if self.options.advanced:
            self.createEntry()

        self.loghandler = LogHandler(self)
        logging.getLogger().addHandler(self.loghandler)

        self.runThread(self.runStartup)

    def createEntry(self):
        self.entry = customtkinter.CTkEntry(self, placeholder_text="Run a command manually...")
        self.entry.grid(row=5, column=0, padx=10, pady=10, sticky="ew")
        self.entry.bind("<Return>", self.entryPressed)

    def entryPressed(self, _):
        cmd = self.entry.get()
        self.setInputEnabled(False)
        self.clearTextbox()
        args = shlex.split(cmd)
        self.currentcmd = args[0]
        self.clicmd = self.cligroup.commands[args[0]]
        self.context = self.clicmd.make_context("tkinter", args[1:])
        self.runThread(self.runClickCommand)

    def changeCommand(self, currentval):
        self.currentcmd = currentval
        if self.currentcmd != self.options.command:
            self.options.command = self.currentcmd
            self.options.options = []
            self.saveOptions()
        for checkbox in self.checkboxes:
            checkbox.destroy()
        self.checkboxes = []
        i = 0
        for param in self.cligroup.commands[self.currentcmd].params:
            if param.is_flag and not param.hidden:
                checkbox = customtkinter.CTkCheckBox(self.checkframe, text=param.opts[0].replace("--", ""), width=75)
                checkbox.grid(row=0, column=i)
                if len(self.options.options) == 0 or checkbox._text in self.options.options:
                    checkbox.toggle()
                # Configure the command after so we don't get a callback from the toggle() above
                checkbox.configure(command=self.changeCheckbox)
                i += 1
                self.checkboxes.append(checkbox)

    def changeCheckbox(self):
        self.options.options = []
        for checkbox in self.checkboxes:
            if checkbox.get():
                self.options.options.append(checkbox._text)
        self.saveOptions()

    def runCommand(self):
        self.setInputEnabled(False)
        self.clearTextbox()
        args = []
        self.clicmd = self.cligroup.commands[self.currentcmd]
        for checkbox in self.checkboxes:
            if checkbox.get():
                args.append("--" + checkbox._text)
        self.context = self.clicmd.make_context("tkinter", args)
        self.runThread(self.runClickCommand)
    
    def runThread(self, func):
        # Set the thread as daemon so it's killed when closing the UI window
        self.thread = threading.Thread(target=lambda loop: loop.run_until_complete(func()), args=(asyncio.new_event_loop(),), daemon=True)
        self.thread.start()

    def clearTextbox(self):
        self.textbox.configure(state=tkinter.NORMAL)
        self.textbox.delete("0.0", tkinter.END)
        self.textbox.configure(state=tkinter.DISABLED)

    def addMessages(self, messages):
        self.textbox.configure(state=tkinter.NORMAL)
        self.textbox.insert(tkinter.END, "\n".join(messages) + "\n")
        self.textbox.configure(state=tkinter.DISABLED)
        self.textbox.yview_moveto("1.0")

    def setInputEnabled(self, enabled):
        state = tkinter.NORMAL if enabled else tkinter.DISABLED
        self.commandmenu.configure(state=state)
        self.menubutton.configure(state=state)
        self.runbutton.configure(state=state)
        if self.options.advanced:
            self.entry.configure(state=state)
        for checkbox in self.checkboxes:
            checkbox.configure(state=state)

    def clickContext(self, choice):
        index = self.advancedlist.index(choice)
        if index == 0:
            if not self.options.advanced:
                self.createEntry()
                self.options.advanced = True
            else:
                self.entry.destroy()
                self.options.advanced = False
        elif index == 1:
            if customtkinter.get_appearance_mode() == "Dark":
                customtkinter.set_appearance_mode("Light")
            else:
                customtkinter.set_appearance_mode("Dark")
            self.options.appearance = customtkinter.get_appearance_mode()
        self.saveOptions()

    def loadOptions(self):
        with open(self.configdir + self.appname + ".json", "r") as f:
            data = f.read()
        try:
            options = json.loads(data)
            self.options = GUIOptions(**options)
        except (json.decoder.JSONDecodeError, TypeError):
            self.options = GUIOptions()
            self.saveOptions()

    def saveOptions(self):
        with open(self.configdir + self.appname + ".json", "w") as f:
            f.write(json.dumps(self.options.__dict__, indent=2))
    
    async def runClickCommand(self):
        if common.runStartup(True):
            try:
                self.clicmd.invoke(self.context)
                finishedmsg = [self.currentcmd.capitalize() + " command executed successfully!"]
                if self.currentcmd == "repack":
                    finishedmsg.append("The repacked game and patch can be found in the " + self.datafolder.rstrip("/") + " folder.")
                elif self.currentcmd == "extract":
                    finishedmsg.append("The extracted files can be found in the " + self.datafolder.rstrip("/") + " folder.")
                self.addMessages(finishedmsg)
            except Exception as e:
                logging.error("", exc_info=True)
        self.setInputEnabled(True)

    async def runStartup(self):
        common.runStartup()
