#!/usr/bin/python
#
# getmail.py Copyright (C) 1999 Charles Cazabon <getmail@discworld.dyndns.org>
#
# Licensed under the GNU General Public License version 2.
#
# getmail is a simple POP3 mail retriever with robust Maildir delivery.
# It is intended as a simple replacement for 'fetchmail' for those people
# who don't need its various and sundry options, bugs, and configuration
# difficulties.
#
# Maildir is the mail storage format designed by Dan Bernstein, author of
# qmail (among other things).  It is supported by many Unix MUAs, including
# mutt (www.mutt.org) and modified versions of pine.
# For more information on the Maildir format,
# see http://cr.yp.to/proto/maildir.html.
#
# getmail returns the number of messages retrieved, or -1 on error.
#

VERSION = '0.2'

#
# Imports
#

import sys, os, string, time, socket, poplib, getopt, termios, TERMIOS
from types import *


#
# Defaults
#
# These can all be overridden with commandline options.
#

DEF_PORT =				110				# Normal POP3 port
DEF_DELETE =			0				# Delete mail after retrieving (0, 1)
DEF_READ_ALL =			0				# Retrieve all mail (1) or just new (0)
DEF_PASSWORD_STDIN =	1				# Read POP3 password from stdin (0, 1)


#
# Options
#

opt_host =				None
opt_port =				DEF_PORT
opt_account =			None
opt_password =			None
opt_password_stdin =	DEF_PASSWORD_STDIN
opt_delete_retrieved =	DEF_DELETE
opt_retrieve_read =		DEF_READ_ALL
opt_maildir =			None
opt_verbose =			0


#
# Data
#

OK, ERROR = (0, -1)

CR =			'\r'
LF =			'\n'
POP3_TERM =		'.'						# POP3 termination octect
deliverycount = 0
argv = sys.argv
stderr = sys.stderr.write

#
# Functions
#

#######################################
def main ():
	'''getmail.py, a POP3 mail retriever.
	Copyright (C) 1999 Charles Cazabon
	Licensed under the GNU General Public License version 2.
	Run without arguments for help.
	'''
	about ()
	parse_options (sys.argv)
	
	shorthost = string.split (opt_host, '.') [0]
	
	try:
		session = poplib.POP3 (opt_host, opt_port)
		if opt_verbose:
			print '%s:  POP3 session initiated' % shorthost
		rc = session.getwelcome ()
		if opt_verbose:
			print '%s:  POP3 greeting:  %s' % (shorthost, rc)
	except poplib.error_proto, response:
		stderr ('%s:  returned greeting "%s"\n' % (shorthost, response))
		sys.exit (ERROR)
	except socket.error, txt:
		stderr ('Exception connecting to %s:  %s\n' % (opt_host, txt))
		sys.exit (ERROR)

	try:
		rc = session.user (opt_account)
		if opt_verbose:
			print '%s:  POP3 user reponse:  %s' % (shorthost, rc)
		rc = session.pass_ (opt_password)
		if opt_verbose:
			print '%s:  POP3 password response:  %s' % (shorthost, rc)
	except poplib.error_proto, response:
		stderr ('%s:  returned "%s" during login\n' % (shorthost, response))
		sys.exit (ERROR)

	# Retrieve message list
	try:
		list = session.list ()
		rc = list[0]
		msglist = list[1]
		if opt_verbose:
			print '%s:  POP3 list response:  %s\n  message list:  %s' \
					% (shorthost, rc, msglist)

		for item in msglist:
			if type (item) == IntType:
				# No more messages; POP3.list() returns a final int
				if opt_verbose:
					print '%s:  finished retrieving messages' % shorthost
				break
			msgnum, msglen = string.split (item)
			if opt_verbose:
				print '  msg %i : len %i' % (int (msgnum), int (msglen))
			result = session.retr (int (msgnum))
			rc = result[0]
			msg = result[1]

			try:
				maildirdeliver (opt_maildir, (unescape_lines (msg)))
			except Error, reason:
				stderr ('Error delivering msg %i len %i:  %s\n'
						% (int (msgnum), int (msglen), reason))
				continue
				
			if opt_verbose:
				print 'delivered msg %i len %i' % (int (msgnum), int (msglen))
			if opt_delete_retrieved:
				rc = session.dele (int (msgnum))
	except poplib.error_proto, response:
		stderr ('%s:  exception "%s" during retrieval/delivery, resetting...\n'
				% (shorthost, response))
		session.rset ()
		session.quit ()
		sys.exit (ERROR)

	if opt_verbose:
		print '%s:  POP3 session completed' % shorthost
	
	session.quit ()

	if opt_verbose:
		print '%s:  POP3 connection closed' % shorthost
		print '%i messages retrieved\n' % deliverycount

	sys.exit (deliverycount)
	

#######################################
def maildirdeliver (maildir, message):
	'Reliably deliver a mail message into a Maildir.'
	# Uses Dan Bernstein's recommended naming convention for maildir delivery
	# See http://cr.yp.to/proto/maildir.html
	global deliverycount
	_time = int (time.time ())
	pid = os.getpid ()
	unique = '%s_%s' % (pid, deliverycount)
	hostname = string.split (socket.gethostname (), '.')[0]
	filename = '%s.%s.%s' % (_time, unique, hostname)
	
	fname_tmp = os.path.join (maildir, 'tmp', filename)
	fname_new = os.path.join (maildir, 'new', filename)

	# Try to open file for reading first
	try:
		f = open (fname_tmp, 'rb')
		f.close ()
		raise 'error:  file "%s" exists' % fname_tmp

	except IOError:
		# Good, file doesn't exist.
		pass
		
	# Open it to write
	try:
		f = open (fname_tmp, 'wb')
		f.writelines (message)
		f.close ()

	except IOError:
		raise 'error: failure writing file "%s"' % fname_tmp
		
	# Move from tmp to new
	try:
		os.rename (fname_tmp, fname_new)

	except OSError:
		raise 'error: failure moving file "%s" to "%s"' \
			   % (fname_tmp, fname_new)

	# Delivery done		
	deliverycount = deliverycount + 1
	return


#######################################
def unescape_lines (raw_lines):
	'''Receive a message in raw POP3 format and convert to internal
	Python format (e.g. EOL convention).  Also strip leading doubled periods,
	and anything trailing the POP3 termination octect (which is '.' surrounded
	by CR+LF pairs).
	'''
	#
	lines = []
	for raw_line in raw_lines:
		line = string.replace (string.replace (raw_line, CR, ''), LF, '')
		if line == POP3_TERM:
			continue
		elif len (line) >= 2 and line[0:1] == '..':
			line = line[1:]
		line = '%s\n' % line
		lines.append (line)
	return lines


#######################################
def about ():
	print 'getmail v.%s\n' \
		  'Copyright (C) 1999 Charles Cazabon <getmail@discworld.dyndns.org>\n' \
		  'Licensed under the GNU General Public License version 2.\n' \
		  % VERSION
	return
	

#######################################
def usage ():
	me = string.strip (os.path.split (sys.argv[0])[-1])
	# Set up default option displays
	def_del = def_dontdel = def_readall = def_readnew = def_stdin = ''
	if DEF_DELETE:			def_del =		'(default)'
	else:					def_dontdel =	'(default)'
	if DEF_READ_ALL:		def_readall =	'(default)'
	else:					def_readnew =	'(default)'
	if DEF_PASSWORD_STDIN:	def_stdin =		'(default)'
	
	stderr ('\n'
	'Usage:  %s <--host value> <--name value> <--pass value | --stdin> \\\n'
	'           <--maildir value> [options]\n\n'
	'Options:\n'
	'  -h or --host <hostname>    POP3 hostname                 (required)\n'
	'  -n or --name <account>     POP3 account name             (required)\n'
	'  -m or --maildir <maildir>  maildir to deliver to         (required)\n'
	'  -P or --port <portnum>     POP3 port                     (default: %i)\n'
	'  -p or --pass <password>    POP3 password\n'
	'  -s or --stdin              read POP3 password from stdin %s\n'
	'  -a or --all                retrieve all messages         %s\n'
	'  -u or --new           (NI) retrieve unread messages      %s\n'
	'  -d or --delete             delete mail after retrieving  %s\n'
	'  -l or --dont-delete        leave mail on server          %s\n'
	'  -v or --verbose            output more information\n'
	'\n  NI : option not yet implemented\n\n'
		% (me, DEF_PORT, def_stdin, def_readall, def_readnew, def_del,
		   def_dontdel))
	return
	
#######################################
def parse_options (argv):
	'''Parse commandline options.  Options handled:
	--delete -d, --dont-delete -l, --all -a, --new -u, --stdin -s,
	--port -P <portnum>,--host -h <hostname>, --name -n <account>,
	--pass -p <password>, --maildir -m <maildir>, --verbose -v
	'''
	#
	global opt_delete_retrieved, opt_retrieve_read, opt_password_stdin, opt_port, \
		opt_host, opt_account, opt_password, opt_maildir, opt_verbose
	error = 0
	optslist, args = [], []

	opts = 'dlausvP:h:n:p:m:'
	longopts = ['delete', 'dont-delete', 'all', 'new', 'stdin', 'port=',
				'host=', 'name=', 'pass=', 'maildir=', 'verbose']
	
	try:
		global optslist, args
		optslist, args = getopt.getopt (argv[1:], opts, longopts)			

	except getopt.error, cause:
		stderr ('Error:  "%s"\n' % cause)
		sys.exit (ERROR)

	for option, value in optslist:
		# parse options
		if option == '--delete' or option == '-d':
			opt_delete_retrieved = 1

		elif option == '--dont-delete' or option == '-l':
			opt_delete_retrieved = 1

		elif option == '--all' or option == '-a':
			opt_retrieve_read = 1

		elif option == '--new' or option == '-u':
			# Not implemented
			opt_retrieve_read = 0

		elif option == '--stdin' or option == '-s':
			opt_password_stdin = 1

		elif option == '--verbose' or option == '-v':
			opt_verbose = 1

		elif option == '--port' or option == '-P':
			if not value:
				stderr ('Error:  option --port supplied without value\n')
				error = 1
			else:
				opt_port = int (value)

		elif option == '--host' or option == '-h':
			if not value:
				stderr ('Error:  option --host supplied without value\n')
				error = 1
			else:
				opt_host = value

		elif option == '--name' or option == '-n':
			if not value:
				stderr ('Error:  option --name supplied without value\n')
				error = 1
			else:
				opt_account = value

		elif option == '--pass' or option == '-p':
			if not value:
				stderr ('Error:  option --pass supplied without value\n')
				error = 1
			else:
				opt_password = value

		elif option == '--maildir' or option == '-m':
			if not value:
				stderr ('Error:  option --maildir supplied without value\n')
				error = 1
			else:
				opt_maildir = value

	# Check mandatory options
	if not opt_host:
		stderr ('Error:  no host supplied\n')
		error = 1
	if not opt_account:
		stderr ('Error:  no account supplied\n')
		error = 1
	if not opt_maildir:
		stderr ('Error:  no maildir supplied\n')
		error = 1

	# Read password from stdin if requested and no --pass option
	if not error and not opt_password and opt_password_stdin:
		fd = sys.stdin.fileno ()
		oldattr = termios.tcgetattr(fd)
		newattr = termios.tcgetattr(fd)
		newattr[3] = newattr[3] & ~TERMIOS.ECHO          # lflags
		try:
			termios.tcsetattr (fd, TERMIOS.TCSADRAIN, newattr)
			opt_password = raw_input ('Enter password:  ')

		finally:
			termios.tcsetattr (fd, TERMIOS.TCSADRAIN, oldattr)
		print

	if not opt_password:
		stderr ('Error:  no password supplied\n')
		error = 1

	if error:
		usage ()
		sys.exit (ERROR)

	return


#######################################
if __name__ == '__main__':
	main ()

					
