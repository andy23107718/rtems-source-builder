#
# RTEMS Tools Project (http://www.rtems.org/)
# Copyright 2010-2013 Chris Johns (chrisj@rtems.org)
# All rights reserved.
#
# This file is part of the RTEMS Tools package in 'rtems-tools'.
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

#
# This code builds a package compiler tool suite given a tool set. A tool
# set lists the various tools. These are specific tool configurations.
#

import copy
import datetime
import distutils.dir_util
import glob
import operator
import os
import sys

try:
    import build
    import check
    import error
    import log
    import options
    import path
    import reports
    import version
except KeyboardInterrupt:
    print 'abort: user terminated'
    sys.exit(1)
except:
    print 'error: unknown application load error'
    sys.exit(1)

class buildset:
    """Build a set builds a set of packages."""

    def __init__(self, bset, _configs, opts, macros = None):
        log.trace('_bset: %s: init' % (bset))
        self.configs = _configs
        self.opts = opts
        if macros is None:
            self.macros = copy.copy(opts.defaults)
        else:
            self.macros = copy.copy(macros)
        self.bset = bset
        self.bset_pkg = '%s-%s-set' % (self.macros.expand('%{_target}'), self.bset)
        self.email_report = ''

    def write_email_report(self, text, prepend = False):
        if len(text) == 0 or text[-1] != '\n' or text[-1] != '\r':
            text += os.linesep
        if prepend:
            self.email_report = text + self.email_report
        else:
            self.email_report += text

    def copy(self, src, dst):
        if not os.path.isdir(path.host(src)):
            raise error.general('copying tree: no source directory: %s' % (path.host(src)))
        if not self.opts.dry_run():
            try:
                files = distutils.dir_util.copy_tree(path.host(src),
                                                     path.host(dst))
                for f in files:
                    log.output(f)
            except IOError, err:
                raise error.general('copying tree: %s -> %s: %s' % (src, dst, str(err)))
            except distutils.errors.DistutilsFileError, err:
                raise error.general('copying tree: %s' % (str(err)))

    def report(self, _config, _build):
        if not _build.opts.get_arg('--no-report') and not _build.opts.get_arg('--no-email'):
            format = _build.opts.get_arg('--report-format')
            if format is None:
                format = 'html'
                ext = '.html'
            else:
                if len(format) != 2:
                    raise error.general('invalid report format option: %s' % ('='.join(format)))
                if format[1] == 'text':
                    format = 'text'
                    ext = '.txt'
                elif format[1] == 'asciidoc':
                    format = 'asciidoc'
                    ext = '.txt'
                elif format[1] == 'html':
                    format = 'html'
                    ext = '.html'
                else:
                    raise error.general('invalid report format: %s' % (format[1]))
            buildroot = _build.config.abspath('%{buildroot}')
            prefix = _build.macros.expand('%{_prefix}')
            name = _build.main_package().name() + ext
            log.notice('reporting: %s -> %s' % (_config, name))
            if not _build.opts.get_arg('--no-report'):
                outpath = path.host(path.join(buildroot, prefix, 'share', 'rtems-source-builder'))
                outname = path.host(path.join(outpath, name))
                r = reports.report(format, self.configs, _build.opts, _build.macros)
                r.setup()
                r.introduction(_build.config.file_name())
                r.config(_build.config, _build.opts, _build.macros)
                if not _build.opts.dry_run():
                    _build.mkdir(outpath)
                    r.write(outname)
                del r
            if not _build.opts.get_arg('--no-email'):
                r = reports.report('text', self.configs, _build.opts, _build.macros)
                r.setup()
                r.introduction(_build.config.file_name())
                r.config(_build.config, _build.opts, _build.macros)
                self.email_report += r.out
                del r

    def root_copy(self, src, dst):
        what = '%s -> %s' % \
            (os.path.relpath(path.host(src)), os.path.relpath(path.host(dst)))
        log.trace('_bset: %s: collecting: %s' % (self.bset, what))
        if not self.opts.dry_run():
            self.copy(src, dst)

    def install(self, name, buildroot, prefix):
        dst = prefix
        src = path.join(buildroot, prefix)
        log.notice('installing: %s -> %s' % (name, path.host(dst)))
        if not self.opts.dry_run():
            self.copy(src, dst)

    def canadian_cross(self, _build):
        # @fixme Switch to using a private macros map.
        macros_to_save = ['%{_prefix}',
                          '%{_tmproot}',
                          '%{buildroot}',
                          '%{_builddir}',
                          '%{_host}']
        macros_to_copy = [('%{_host}',     '%{_build}'),
                          ('%{_tmproot}',  '%{_tmpcxcroot}'),
                          ('%{buildroot}', '%{buildcxcroot}'),
                          ('%{_builddir}', '%{_buildcxcdir}')]
        orig_macros = {}
        for m in macros_to_save:
            orig_macros[m] = _build.config.macro(m)
        for m in macros_to_copy:
            _build.config.set_define(m[0], _build.config.macro(m[1]))
        _build.make()
        for m in macros_to_save:
            _build.config.set_define(m, orig_macros[m])
        self.root_copy(_build.config.expand('%{buildcxcroot}'),
                       _build.config.expand('%{_tmpcxcroot}'))

    def build_package(self, _config, _build):
        if _build.canadian_cross():
            self.canadian_cross(_build)
        _build.make()
        self.report(_config, _build)
        self.root_copy(_build.config.expand('%{buildroot}'),
                       _build.config.expand('%{_tmproot}'))

    def bset_tar(self, _build):
        tardir = _build.config.expand('%{_tardir}')
        if self.opts.get_arg('--bset-tar-file'):
            path.mkdir(tardir)
            tar = path.join(tardir, _build.config.expand('%s.tar.bz2' % (self.bset_pkg)))
            log.notice('tarball: %s' % (os.path.relpath(path.host(tar))))
            if not self.opts.dry_run():
                tmproot = _build.config.expand('%{_tmproot}')
                cmd = _build.config.expand("'cd " + tmproot + \
                                               " && %{__tar} -cf - . | %{__bzip2} > " + tar + "'")
                _build.run(cmd, shell_opts = '-c', cwd = tmproot)

    def parse(self, bset):

        def _clean(line):
            line = line[0:-1]
            b = line.find('#')
            if b >= 0:
                line = line[1:b]
            return line.strip()

        bsetname = bset

        if not path.exists(bsetname):
            for cp in self.macros.expand('%{_configdir}').split(':'):
                configdir = path.abspath(cp)
                bsetname = path.join(configdir, bset)
                if path.exists(bsetname):
                    break
                bsetname = None
            if bsetname is None:
                raise error.general('no build set file found: %s' % (bset))
        try:
            log.trace('_bset: %s: open: %s' % (self.bset, bsetname))
            bset = open(path.host(bsetname), 'r')
        except IOError, err:
            raise error.general('error opening bset file: %s' % (bsetname))

        configs = []

        try:
            lc = 0
            for l in bset:
                lc += 1
                l = _clean(l)
                if len(l) == 0:
                    continue
                log.trace('_bset: %s: %03d: %s' % (self.bset, lc, l))
                ls = l.split()
                if ls[0][-1] == ':' and ls[0][:-1] == 'package':
                    self.bset_pkg = self.macros.expand(ls[1].strip())
                    self.macros['package'] = self.bset_pkg
                elif ls[0][0] == '%':
                    if ls[0] == '%define':
                        if len(ls) > 2:
                            self.macros.define(ls[1].strip(),
                                               ' '.join([f.strip() for f in ls[2:]]))
                        else:
                            self.macros.define(ls[1].strip())
                    elif ls[0] == '%undefine':
                        if len(ls) > 2:
                            raise error.general('%undefine requires just the name')
                        self.macros.undefine(ls[1].strip())
                    elif ls[0] == '%include':
                        configs += self.parse(ls[1].strip())
                    else:
                        raise error.general('invalid directive in build set files: %s' % (l))
                else:
                    l = l.strip()
                    c = build.find_config(l, self.configs)
                    if c is None:
                        raise error.general('cannot find file: %s' % (l))
                    configs += [c]
        except:
            bset.close()
            raise

        bset.close()

        return configs

    def load(self):

        #
        # If the build set file ends with .cfg the user has passed to the
        # buildset builder a configuration so we just return it.
        #
        if self.bset.endswith('.cfg'):
            configs = [self.bset]
        else:
            exbset = self.macros.expand(self.bset)
            self.macros['_bset'] = exbset
            root, ext = path.splitext(exbset)
            if exbset.endswith('.bset'):
                bset = exbset
            else:
                bset = '%s.bset' % (exbset)
            configs = self.parse(bset)
        return configs

    def build(self, deps = None):

        log.trace('_bset: %s: make' % (self.bset))
        log.notice('Build Set: %s' % (self.bset))

        if not self.opts.get_arg('--no-email'):
            email_report_header = \
                'Build Set: %s (%s)' % (self.bset, datetime.datetime.now().ctime())

        configs = self.load()

        log.trace('_bset: %s: configs: %s'  % (self.bset, ','.join(configs)))

        current_path = os.environ['PATH']

        start = datetime.datetime.now()

        try:
            builds = []
            for s in range(0, len(configs)):
                try:
                    #
                    # Each section of the build set gets a separate set of
                    # macros so we do not contaminate one configuration with
                    # another.
                    #
                    opts = copy.copy(self.opts)
                    macros = copy.copy(self.macros)
                    if configs[s].endswith('.bset'):
                        log.trace('_bset: %s' % ('=' * 80))
                        bs = buildset(configs[s], self.configs, opts, macros)
                        bs.build(deps)
                        del bs
                    elif configs[s].endswith('.cfg'):
                        log.trace('_bset: %s' % ('-' * 80))
                        b = build.build(configs[s], self.opts.get_arg('--pkg-tar-files'),
                                        opts, macros)
                        if deps is None:
                            self.build_package(configs[s], b)
                            if s == len(configs) - 1:
                                self.bset_tar(b)
                        else:
                            deps += b.config.includes()
                        builds += [b]
                    else:
                        raise error.general('invalid config type: %s' % (configs[s]))
                except error.general, gerr:
                    self.write_email_report(str(gerr))
                    if self.opts.keep_going():
                        print gerr
                        if self.opts.always_clean():
                            builds += [b]
                    else:
                        raise
            if deps is None and not self.opts.no_install():
                for b in builds:
                    self.install(b.name(),
                                 b.config.expand('%{buildroot}'),
                                 b.config.expand('%{_prefix}'))
            if deps is None and \
                    (not self.opts.no_clean() or self.opts.always_clean()):
                for b in builds:
                    log.notice('cleaning: %s' % (b.name()))
                    b.cleanup()
            for b in builds:
                del b
        except:
            os.environ['PATH'] = current_path
            raise

        end = datetime.datetime.now()

        os.environ['PATH'] = current_path

        log.notice('Build Set: Time %s' % (str(end - start)))

        if not self.opts.get_arg('--no-email'):
            self.write_email_report('', True)
            self.write_email_report('  Build Time %s' % (str(end - start)), True)
            self.write_email_report(email_report_header, True)

def list_bset_cfg_files(opts, configs):
    if opts.get_arg('--list-configs') or opts.get_arg('--list-bsets'):
        if opts.get_arg('--list-configs'):
            ext = '.cfg'
        else:
            ext = '.bset'
        for p in configs['paths']:
            print 'Examining: %s' % (os.path.relpath(p))
        for c in configs['files']:
            if c.endswith(ext):
                print '    %s' % (c)
        return True
    return False

def run():
    import sys
    try:
        optargs = { '--list-configs':  'List available configurations',
                    '--list-bsets':    'List available build sets',
                    '--list-deps':     'List the dependent files.',
                    '--bset-tar-file': 'Create a build set tar file',
                    '--pkg-tar-files': 'Create package tar files',
                    '--no-report':     'Do not create a package report.',
                    '--report-format': 'The report format (text, html, asciidoc).',
                    '--no-email':      'Do not send an email report.',
                    '--smtp-host':     'SMTP host to send via.',
                    '--email-to':      'Email address to send the email too.',
                    '--email-from':    'Email address the report is from.' }
        opts = options.load(sys.argv, optargs)
        log.notice('RTEMS Source Builder - Set Builder, v%s' % (version.str()))
        if not check.host_setup(opts):
            raise error.general('host build environment is not set up correctly')
        configs = build.get_configs(opts)
        if opts.get_arg('--list-deps'):
            deps = []
        else:
            deps = None
        if not list_bset_cfg_files(opts, configs):
            prefix = opts.defaults.expand('%{_prefix}')
            if not opts.dry_run() and not opts.no_install() and \
                    not path.ispathwritable(prefix):
                raise error.general('prefix is not writable: %s' % (path.host(prefix)))
            for bset in opts.params():
                b = buildset(bset, configs, opts)
                b.build(deps)
                del b
        if deps is not None:
            c = 0
            for d in sorted(set(deps)):
                c += 1
                print 'dep[%d]: %s' % (c, d)
    except error.general, gerr:
        print gerr
        print >> sys.stderr, 'Build FAILED'
        sys.exit(1)
    except error.internal, ierr:
        print ierr
        sys.exit(1)
    except error.exit, eerr:
        pass
    except KeyboardInterrupt:
        log.notice('abort: user terminated')
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    run()
