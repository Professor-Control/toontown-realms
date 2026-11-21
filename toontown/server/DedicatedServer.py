import atexit
import os
import subprocess
import sys
import time

from direct.directnotify import DirectNotifyGlobal
from otp.otpbase import OTPLocalizer, OTPGlobals

ASTRON_DONE_MSG = 'Event Logger: Opened new log.'
UBERDOG_DONE_MSG = 'ToontownUberRepository: Done.'
AI_DONE_MSG = 'District is now ready. Have fun in Toontown Realms!'
AI_ZONE_MSG = 'Creating zone... '


class DedicatedServer:
    notify = DirectNotifyGlobal.directNotify.newCategory('DedicatedServer')

    def __init__(self, isLocal=False):
        self.isLocal = isLocal
        self.astronProcess = None
        self.astronLog = None
        self.uberDogProcess = None
        self.uberDogLog = None
        self.aiProcess = None
        self.aiLog = None
        self.env = os.environ.copy()

    def start(self):
        # Before we do anything, register self.killProcesses with atexit so that in the event of a hard exit,
        # the server processes are still killed if they are running.
        atexit.register(self.killProcesses)

        if self.isLocal:
            self.env['TTOFF_GAME_MODE'] = str(OTPGlobals.ModeOffline)
            self.notify.info('Starting local server...')
        else:
            self.env['TTOFF_GAME_MODE'] = str(OTPGlobals.ModeServer)
            self.notify.info('Starting dedicated server...')

        # Astron.
        self.notify.info('Starting Astron...')

        # Generate a log file for the current Astron session.
        astronLogFile = self.generateLog('astron')

        # Open that log file and use it.
        self.astronLog = open(astronLogFile, 'a')
        self.notify.info('Opened new Astron log: %s' % astronLogFile)

        # Let's show the user that we're starting up Astron.
        try:
            gameServicesDialog.bar['text'] = OTPLocalizer.CRLoadingGameServicesAstron
        except NameError:
            self.notify.info(OTPLocalizer.CRLoadingGameServices + '\n\n' + OTPLocalizer.CRLoadingGameServicesAstron)

        astronConfig = config.GetString('astron-config-path', 'astron/config/astrond.yml')

        # Start Astron process.
        if sys.platform == 'win32':
            # Sometimes Astron fails to close if the game closes from a memory leak;
            # this also comes in handy if Astron takes too long to start
            self.killWindowProcess(processName='astrond.exe')

            self.astronProcess = subprocess.Popen('astron\\astrond.exe --loglevel info {0}'.format(astronConfig.replace('/', '\\')),
                                                  stdout=self.astronLog, stderr=subprocess.STDOUT)
        elif sys.platform == 'linux':
            # If we encounter any scenario where we need to kill Astron on Linux
            # cuz it doesn't shutdown after previously closing the game
            # (I'm thinking this is only necessary on Windows so I'm not doing it here)
            # killall -9 astrond-linux
            self.astronProcess = subprocess.Popen(
                ['./astron/astrond-linux', '--loglevel', 'info', astronConfig],
                stdout=self.astronLog, stderr=subprocess.STDOUT)
        else:
            # Assuming Darwin (macOS)
            # If we encounter any scenario where we need to kill Astron on Mac
            # cuz it doesn't shutdown after previously closing the game
            # (I'm thinking this is only necessary on Windows so I'm not doing it here)
            # killall -9 astrond-darwin
            self.astronProcess = subprocess.Popen(
                ['./astron/astrond-darwin', '--loglevel', 'info', astronConfig],
                stdout=self.astronLog, stderr=subprocess.STDOUT,
                env={'DYLD_LIBRARY_PATH': './astron/lib'})

        # Setup a Task to start the UberDOG process when Astron is done.
        taskMgr.add(self.startUberDog, 'start-uberdog-task')

    def startUberDog(self, task):
        # Check if Astron is ready through the log.
        with open(self.astronLog.name, 'r') as f:
            astronLogData = f.read()
        if ASTRON_DONE_MSG not in astronLogData:
            # Oh no, Astron is not ready yet!
            if task.time >= 6.0:
                # we timed out on Windows; attempt a restart.
                if sys.platform == 'win32':
                    self.notify.warning("Astron failed to start in time; attempting a restart...")
                    self.start()
                    return task.done
            # Run the task again.
            return task.again

        # Cool, Astron is ready!
        self.notify.info('Astron started successfully!')

        # UberDOG.
        self.notify.info('Starting UberDOG server...')

        # Generate a log file for the current UberDOG session.
        uberDogLogFile = self.generateLog('uberdog')

        # Open that log file and use it.
        self.uberDogLog = open(uberDogLogFile, 'a')
        self.notify.info('Opened new UberDOG log: %s' % uberDogLogFile)

        # Setup initial UberDOG arguments.
        if __debug__:
            uberDogArguments = f'{sys.executable} -m toontown.uberdog.UDStart'
        else:
            if sys.platform == 'win32':
                uberDogArguments = 'offline.exe --uberdog'
            elif sys.platform == 'linux':
                uberDogArguments = ['./offline', '--uberdog']
            else:
                # Assuming Darwin (macOS)
                uberDogArguments = ['./ToontownOffline', '--uberdog']

        # Let's show the user that we're starting up UberDOG.
        try:
            gameServicesDialog.bar['text'] = OTPLocalizer.CRLoadingGameServicesUberdog
        except NameError:
            self.notify.info(OTPLocalizer.CRLoadingGameServices + '\n\n' + OTPLocalizer.CRLoadingGameServicesUberdog)

        # Start UberDOG process.
        if __debug__:
            self.uberDogProcess = subprocess.Popen(uberDogArguments, stdout=self.uberDogLog,
                                                   stderr=subprocess.STDOUT,
                                                   shell=(True if not sys.platform == 'win32' else False),
                                                   env=self.env)
        else:
            self.uberDogProcess = subprocess.Popen(uberDogArguments, stdout=self.uberDogLog,
                                                   stderr=subprocess.STDOUT, env=self.env)

        # Setup a Task to start the AI process when the UberDOG is done.
        taskMgr.add(self.startAI, 'start-ai-task')

        # Otherwise, we're done with this task.
        return task.done

    def startAI(self, task):
        # Check if the UberDOG is ready through the log.
        with open(self.uberDogLog.name, 'r') as f:
            uberDogLogData = f.read()
        if UBERDOG_DONE_MSG not in uberDogLogData:
            # Oh no, the UberDOG is not ready yet! Run the task again.
            return task.again

        # Cool, the UberDOG is ready!
        self.notify.info('UberDOG started successfully!')

        # AI.
        self.notify.info('Starting AI server...')

        # Generate a log file for the current AI session...
        aiLogFile = self.generateLog('ai')

        # Open that log file and use it.
        self.aiLog = open(aiLogFile, 'a')
        self.notify.info('Opened new AI log: %s' % aiLogFile)

        # Setup initial AI arguments.
        if __debug__:
            aiArguments = f'{sys.executable} -m toontown.ai.AIStart'
        else:
            if sys.platform == 'win32':
                aiArguments = 'offline.exe --ai'
            elif sys.platform == 'linux':
                aiArguments = ['./offline', '--ai']
            else:
                # Assuming Darwin (macOS)
                aiArguments = ['./ToontownOffline', '--ai']

        # Let's show the user that we're starting up AI.
        try:
            gameServicesDialog.bar['text'] = OTPLocalizer.CRLoadingGameServicesAI
        except NameError:
            self.notify.info(OTPLocalizer.CRLoadingGameServices + '\n\n' + OTPLocalizer.CRLoadingGameServicesAI)

        # Start AI process.
        if __debug__:
            self.aiProcess = subprocess.Popen(aiArguments, stdout=self.aiLog, stderr=subprocess.STDOUT,
                                              shell=(True if not sys.platform == 'win32' else False),
                                              env=self.env)
        else:
            self.aiProcess = subprocess.Popen(aiArguments, stdout=self.aiLog, stderr=subprocess.STDOUT, env=self.env)

        # Setup a Task to send the done message when the AI is done.
        taskMgr.add(self.serverStarted, 'server-started-task')

        # Otherwise, we're done with this task.
        return task.done

    def serverStarted(self, task):
        # Check if the AI is ready through the log.
        with open(self.aiLog.name, 'r') as f:
            aiLogData = f.read()
        if AI_DONE_MSG not in aiLogData:
            # Oh no, the AI is not ready yet! Run the task again.
            return task.again

        # Cool, the AI is ready!
        self.notify.info('AI started successfully!')

        # All of the servers are running! Let's send the done message.
        self.notify.info('Server is now ready. Have fun in Toontown Realms!')
        if self.isLocal:
            messenger.send('localServerReady')

        # Setup a Task to check if the server has crashed.
        taskMgr.add(self.checkForCrashes, 'check-for-crashes-task')

        # Otherwise, we're done with this task.
        return task.done

    def checkForCrashes(self, task):
        # Check if the UberDOG server has crashed.
        if self.uberDogProcess.poll() is not None:
            self.killProcesses()
            if hasattr(base, 'cr'):
                # theres def a better way to do this, quick patch for now
                if base.cr.loginFSM.getCurrentState().getName() == 'mainMenu':
                    return task.done
            self.notify.error("Oh no, this realm has crashed!\n\n"
                              "The UberDOG server has crashed, and you will need to restart your realm."
                              "\n\nIf this problem persists, please contact a developer and provide "
                              "them with your most recent log from the \"logs/uberdog\" folder.")
            return task.done

        # Check if the AI server has crashed.
        if self.aiProcess.poll() is not None:
            self.killProcesses()
            if hasattr(base, 'cr'):
                if base.cr.loginFSM.getCurrentState().getName() == 'mainMenu':
                    return task.done
            self.notify.error("Oh no, this realm has crashed!\n\n"
                              "The AI server has crashed, and you will need to restart your realm.\n\n"
                              "If this problem persists, please contact a developer and provide "
                              "them with your most recent log from the \"logs/ai\" folder.")

            return task.done

        # Keep running this Task if the server has not crashed.
        return task.again

    def killProcesses(self):
        # Terminate server processes in reverse order of how they were started, starting with the AI.
        if sys.platform == 'win32':
            # windows is inferior, gotta handle it differently
            if self.aiProcess and self.aiProcess.poll() is None:
                # we only run terminate, since apparently kill = terminate on Windows
                self.aiProcess.terminate()
                # force Windows to kill this process
                if self.aiProcess.poll() is None:
                    self.killWindowProcess(self.aiProcess)

            # Now for UberDOG.
            if self.uberDogProcess and self.uberDogProcess.poll() is None:
                self.uberDogProcess.terminate()
                # force Windows to kill this process
                if self.uberDogProcess.poll() is None:
                    self.killWindowProcess(self.uberDogProcess)

            # And lastly, Astron.
            if self.astronProcess and self.astronProcess.poll() is None:
                self.astronProcess.terminate()
                # force Windows to kill this process
                if self.astronProcess.poll() is None:
                    self.killWindowProcess(self.astronProcess)
        else:
            if self.aiProcess and self.aiProcess.poll() is None:
                self.aiProcess.kill()
                if self.aiProcess.poll() is None:
                    # only terminate if we have to
                    self.aiProcess.terminate()

            # Now for UberDOG.
            if self.uberDogProcess and self.uberDogProcess.poll() is None:
                self.uberDogProcess.kill()
                if self.uberDogProcess.poll() is None:
                    # only terminate if we have to
                    self.uberDogProcess.terminate()

            # And lastly, Astron.
            if self.astronProcess and self.astronProcess.poll() is None:
                self.astronProcess.kill()
                if self.astronProcess.poll() is None:
                    # only terminate if we have to
                    self.astronProcess.terminate()

    # this one is for the *especially* worthless Windows processes that just won't die...
    def killWindowProcess(self, winProcess=None, processName=None):
        if sys.platform != 'win32':
            # this is for worthless Windows processes that won't die, not the superior *nix systems
            return
        if all(x is None for x in (winProcess, processName)):
            self.notify.warning("Nothing to use to terminate Windows process.")
            return
        if winProcess is not None and winProcess.poll() is None:
            if not isinstance(winProcess, subprocess.Popen):
                self.notify.warning("Windows process must be of type subprocess.Popen.")
                return
            killProcess = subprocess.Popen(f'taskkill /F /PID {winProcess.pid}', stderr=subprocess.DEVNULL,
                                           env=self.env, shell=True)
            killProcess.communicate()
        elif processName is not None:
            if not isinstance(processName, str) or processName.strip() == '':
                self.notify.warning("Windows process name must be a non-empty string.")
                return
            killProcess = subprocess.Popen(f'taskkill /IM "{processName}" /F', stderr=subprocess.DEVNULL,
                                           env=self.env, shell=True)
            killProcess.communicate()

    @staticmethod
    def generateLog(logPrefix):
        ltime = 1 and time.localtime()
        logSuffix = '%02d%02d%02d_%02d%02d%02d' % (ltime[0] - 2000, ltime[1], ltime[2],
                                                   ltime[3], ltime[4], ltime[5])

        if not os.path.exists('logs/'):
            os.mkdir('logs/')

        if not os.path.exists('logs/%s/' % logPrefix):
            os.mkdir('logs/%s/' % logPrefix)

        logFile = 'logs/%s/%s-%s.log' % (logPrefix, logPrefix, logSuffix)

        return logFile
