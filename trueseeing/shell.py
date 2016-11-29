import os
import sys
import getopt
import configparser
import logging
import collections
import concurrent.futures

import trueseeing.signature.base
import trueseeing.exploit
import trueseeing.grab

from trueseeing.context import Context

log = logging.getLogger(__name__)

preferences = None
signatures = collections.OrderedDict([cl.as_signature() for cl in trueseeing.signature.base.SignatureClasses().extracted()])

signatures_all = set(signatures.keys())
signatures_default = signatures_all.copy()

def formatted(issue):
  if not (issue.row is None or issue.col is None):
    return '%(source)s:%(row)d:%(col)d:%(severity)s{%(confidence)s}:%(description)s [-W%(detector_id)s]' % issue.__dict__
  else:
    return '%(source)s:0:0:%(severity)s{%(confidence)s}:%(description)s [-W%(detector_id)s]' % issue.__dict__

def apply_detector(context, c):
  found = False
  for e in (formatted(e) for e in c(context).detect()):
    found = True
    print(e)
  return found

def processed(apkfilename, chain):
  with Context() as context:
    context.analyze(apkfilename)
    log.info("%s -> %s" % (apkfilename, context.wd))

    found = False

    with concurrent.futures.ProcessPoolExecutor() as pool:
      futures = [pool.submit(apply_detector, context, c) for c in chain]
      for f in concurrent.futures.as_completed(futures):
        if f.exception() is not None:
          raise f.exception()
        else:
          found |= f.result()

    return found

def selected_signatures_on(switch):
  if switch != 'all':
    if not switch.endswith('-all'):
      return set([switch])
    else:
      return {v for v in signatures_all if v.startswith(switch.replace('-all', ''))}
  else:
    return signatures_all

def shell(argv):
  log_level = logging.INFO
  signature_selected = signatures_default.copy()
  exploitation_mode = ''
  fingerprint_mode = False
  grab_mode = False
  inspection_mode = False

  try:
    opts, files = getopt.getopt(sys.argv[1:], 'dW:', ['exploit-resign', 'exploit-unsign', 'exploit-enable-debug', 'exploit-enable-backup', 'fingerprint', 'grab', 'inspect'])
    for o, a in opts:
      if o in ['-d']:
        log_level = logging.DEBUG
      if o in ['-W']:
        if a.startswith('no-'):
          signature_selected.difference_update(selected_signatures_on(a[3:]))
        else:
          signature_selected.update(selected_signatures_on(a))

      if o in ['--exploit-resign']:
        exploitation_mode = 'resign'
      if o in ['--exploit-unsign']:
        exploitation_mode = 'unsign'
      if o in ['--exploit-enable-debug']:
        exploitation_mode = 'enable-debug'
      if o in ['--exploit-enable-backup']:
        exploitation_mode = 'enable-backup'
      if o in ['--grab']:
        grab_mode = True
      if o in ['--fingerprint']:
        fingerprint_mode = True
      if o in ['--inspect']:
        inspection_mode = True
  except IndexError:
    print("%s: no input files" % argv[0])
    return 2
  else:
    global preferences
    preferences = configparser.ConfigParser()
    preferences.read('.trueseeingrc')

    logging.basicConfig(level=log_level, format="%(msg)s")

    if not exploitation_mode:
      if not any([fingerprint_mode, grab_mode, inspection_mode]):
        error_found = False
        for f in files:
          if processed(f, [v for k,v in signatures.items() if k in signature_selected]):
            error_found = True
        if not error_found:
          return 0
        else:
          return 1
      elif fingerprint_mode:
        for f in files:
          print('%s: %s' % (f, Context().fingerprint_of(f)))
      elif grab_mode:
        if files:
          for pkg in files:
            if trueseeing.grab.Grab(pkg).exploit():
              print('%s: package saved: %s.apk' % (sys.argv[0], pkg))
              return 0
            else:
              print('%s: package not found' % sys.argv[0])
              return 1
        else:
          print('%s: listing packages' % sys.argv[0])
          for p in sorted(trueseeing.grab.Grab(None).list_()):
            print(p)
          return 0
      elif inspection_mode:
        f = files[0]
        with Context() as context:
          print("inspection mode; analyzing %s" % f)
          context.analyze(f)
          print("analyzed, context in 'context'")
          from IPython import embed
          embed()
    elif exploitation_mode == 'resign':
      for f in files:
        trueseeing.exploit.ExploitResign(f, os.path.basename(f).replace('.apk', '-resigned.apk')).exploit()
      return 0
    elif exploitation_mode == 'unsign':
      for f in files:
        trueseeing.exploit.ExploitUnsign(f, os.path.basename(f).replace('.apk', '-unsigned.apk')).exploit()
      return 0
    elif exploitation_mode == 'enable-debug':
      for f in files:
        trueseeing.exploit.ExploitEnableDebug(f, os.path.basename(f).replace('.apk', '-debuggable.apk')).exploit()
      return 0
    elif exploitation_mode == 'enable-backup':
      for f in files:
        trueseeing.exploit.ExploitEnableBackup(f, os.path.basename(f).replace('.apk', '-backupable.apk')).exploit()
      return 0

def entry():
  import sys
  return shell(sys.argv)
