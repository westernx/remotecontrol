import code
import logging
import sys
import threading

from . import core
from . import threads

_locals = threading.local()


def use_main_thread(v):
    interpreter = getattr(_locals, 'interpreter', None)
    if interpreter:
        interpreter.use_main_thread = bool(v)


class Interpreter(code.InteractiveConsole):
    
    def __init__(self, server, sock, addr, locals, call_in_main_thread=None):

        # Would be nice to user super, but it doesn't inheric from object
        # so no dice.
        code.InteractiveConsole.__init__(self, locals={} if locals is None else locals)

        self.server = server
        self.sock = sock
        self.addr = addr
        self.file = core.fileobject(sock)

        self.use_main_thread = True
        if call_in_main_thread:
            self._call_in_main_thread = call_in_main_thread
        
    def raw_input(self, prompt):
        
        self.sock.sendall(prompt)
        
        # We will get an empty string when the connection has closed. We must 
        # manually throw an EOFError (which the super will handle), otherwise
        # the socket will complain of a bad pipe when it tries to write the
        # next prompt.
        x = self.file.readline()
        if not x:
            raise EOFError()
        return x
    
    def write(self, content):
        try:
            self.sock.sendall(content)
        except:
            sys.__stdout__.write('error while writing %r\n' % content)
            sys.__stdout__.flush()
            raise
    
    def push(self, line):

        # See caveats.
        with core.replace_stdio(self.file, self.file, self.file):
            return code.InteractiveConsole.push(self, line)
    
    def runsource(self, source, *args):
        
        # Fix a shortcoming of the super class: it does not handle multiple
        # lines in control flow the same way that the "real" interpreter does.
        # Assert that if we are in some control flow then the last line must be
        # empty before we attempt to exec it.
        lines = source.splitlines()
        if len(lines) > 1 and lines[-1].strip():
            return True
        
        if self.use_main_thread:
            return self._call_in_main_thread(self._runsource, source, *args)
        else:
            return self._runsource(source, *args)

    def _call_in_main_thread(self, func, *args):
        return threads.call_in_main_thread(func, *args)

    def _runsource(self, source, *args):
        _locals.interpreter = self
        return code.InteractiveInterpreter.runsource(self, source, *args)
    
    def interact(self):
        try:
            code.InteractiveConsole.interact(self)
        finally:
            self.server.debug('shutting down client %s', self.addr)
            self.sock.close()
            self.file.close # WTF?


class Server(core.Server):

    client_class = Interpreter



def listen(addr, locals=None, server_class=Server, **kwargs):
    console = server_class(addr, locals, **kwargs)
    console.listen()


def spawn(*args, **kwargs):
    thread = threading.Thread(target=listen, args=args, kwargs=kwargs)
    thread.daemon = True
    thread.start()
    return thread


if __name__ == '__main__':

    addr = sys.argv[1] if len(sys.argv) > 1 else '9000'
    addr = int(addr) if addr.isdigit() else addr
    listen(addr, {})


