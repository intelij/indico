# This file is part of Indico.
# Copyright (C) 2002 - 2017 European Organization for Nuclear Research (CERN).
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# Indico is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Indico; if not, see <http://www.gnu.org/licenses/>.

"""
This file contains functions used by both 'python setup.py install' and after-easy_install
based installations.
"""

import commands
import os
import re
import shutil
import sys
import pkg_resources

if sys.platform == 'linux2':
    import pwd
    import grp

import indico


# Egg directory + etc/indico.conf
PWD_INDICO_CONF = os.path.abspath(os.path.join(os.path.split(os.path.dirname(indico.__file__))[0],
                                               'etc', 'indico.conf'))


def createDirs(directories):
    '''Creates directories that are not automatically created by setup.install or easy_install'''
    for d in ['log', 'tmp', 'cache']:
        if not os.path.exists(directories[d]):
            os.makedirs(directories[d])


def compileAllLanguages(cmd):
    '''Generates .mo files from .po files'''

    try:
        pkg_resources.require('babel')
    except pkg_resources.DistributionNotFound:
        print """
Babel not found! Babel is needed for internationalization if you're building Indico from source. Please install it and re-run this program.
i.e. try 'easy_install babel'"""
        sys.exit(-1)

    # call command directly
    cc = cmd.distribution.get_command_obj('compile_catalog')
    cc.run()


def copyTreeSilently(source, target):
    '''Copies source tree to target tree overwriting existing files'''
    source = os.path.normpath(source)
    target = os.path.normpath(target)
    for root, dirs, files in os.walk(source, topdown=False):
        for name in files:
            fullpath = os.path.normpath(os.path.join(root, name))
            dstfile = os.path.normpath(fullpath.replace(source, target))
            targetdir = os.path.dirname(dstfile)
            if not os.path.exists(targetdir):
                os.makedirs(targetdir)
            try:
                shutil.copy(fullpath, dstfile)
            except Exception, e:
                print e


def _checkModPythonIsInstalled():
    pass


def _guessApacheUidGid():

    finalUser, finalGroup = None, None

    for username in ['apache', 'www-data', 'www']:
        try:
            finalUser = pwd.getpwnam(username)
            break
        except KeyError:
            pass

    for groupname in ['apache', 'www-data', 'www']:
        try:
            finalGroup = grp.getgrnam(groupname)
            break
        except KeyError:
            pass

    return finalUser, finalGroup

def _findApacheUserGroup(uid, gid):
        # if we are on linux we need to give proper permissions to the results directory
    if sys.platform == "linux2":
        prompt = True

        # Check to see if uid/gid were provided through commandline
        if uid and gid:
            try:
                accessuser = pwd.getpwuid(int(uid)).pw_name
                accessgroup = grp.getgrgid(int(gid)).gr_name
                prompt = False
            except KeyError:
                print 'uid/gid pair (%s/%s) provided through command line is false' % (uid, gid)
        else:
            print "uid/gid not provided. Trying to guess them... ",
            uid, gid = _guessApacheUidGid()
            if uid and gid:
                print "found %s(%s) %s(%s)" % (uid.pw_name, uid.pw_uid,
                                         gid.gr_name, gid.gr_gid)
                accessuser = uid.pw_name
                accessgroup = gid.gr_name
                prompt = False

        if prompt == True:
            valid_credentials = False
            while not valid_credentials:
                accessuser = raw_input("\nPlease enter the user that will be running the Apache server: ")
                accessgroup = raw_input("\nPlease enter the group that will be running the Apache server: ")
                try:
                    pwd.getpwnam(accessuser)
                    grp.getgrnam(accessgroup)
                    valid_credentials = True
                except KeyError:
                    print "\nERROR: Invalid user/group pair (%s/%s)" % (accessuser, accessgroup)

        return accessuser, accessgroup
    else: #for windows
        return "apache", "apache"


def _checkDirPermissions(directories, accessuser=None, accessgroup=None):
    '''Makes sure that directories which need write access from Apache have
    the correct permissions

    - uid and gid: if they are valid user_ids and group_ids they will be used to chown
        the directories instead of the indico.conf ones.
    '''

    print "\nWe need to 'sudo' in order to set the permissions of some directories..."

    if sys.platform == "linux2":
        dirs2check = list(directories[x] for x in ['htdocs', 'log', 'tmp', 'cache'] if directories.has_key(x))
        for dir in dirs2check:
            stat_info = os.stat(dir)
            if pwd.getpwuid(int(stat_info.st_uid)).pw_name != accessuser or os.path.basename(dir) == 'htdocs':
                print commands.getoutput("if test $(which sudo); then CMD=\"sudo\"; fi; $CMD chown -R %s:%s %s" % (accessuser, accessgroup, dir))
            elif grp.getgrgid(int(stat_info.st_gid)).gr_name != accessgroup:
                os.chown(dir, pwd.getpwnam(accessuser).pw_uid, grp.getgrnam(accessgroup).gr_gid)


def _extractDirsFromConf(conf):
    execfile(conf)
    values = locals().copy()

    return {'bin': values['BinDir'],
            'etc': values['ConfigurationDir'],
            'htdocs': values['HtdocsDir'],
            'tmp': values['UploadedFilesTempDir'],
            'log': values['LogDir'],
            'cache': values['XMLCacheDir']}

def _replacePrefixInConf(filePath, prefix):
    fdata = open(filePath).read()
    fdata = re.sub(r'/opt/indico', prefix, fdata)
    fdata = re.sub(r"^#\s*SecretKey = ''", "SecretKey = {!r}".format(os.urandom(32)), fdata)
    open(filePath, 'w').write(fdata)


def indico_pre_install(defaultPrefix, existingConfig=None):
    """
    defaultPrefix is the default prefix dir where Indico will be installed
    """

    upgrade = False

    # Configuration specified in the command-line
    if existingConfig:
        existing = existingConfig
        # upgrade is mandatory
        upgrade = True

    if upgrade:
        print 'Upgrading the existing Indico installation..'
        return _extractDirsFromConf(existing)
    else:
        # then, in case no previous installation exists
        return fresh_install(defaultPrefix)


def fresh_install(defaultPrefix):

    # start from scratch
    print "No previous installation of Indico was found."
    print "Please specify a directory prefix:"

    # ask for a directory prefix
    prefixDir = raw_input('[%s]: ' % defaultPrefix).strip()

    if prefixDir == '':
        prefixDir = defaultPrefix

    configDir = os.path.join(prefixDir, 'etc')

    # create the directory that will contain the configuration files
    if not os.path.exists(configDir):
            os.makedirs(configDir)

    indicoconfpath = os.path.join(configDir, 'indico.conf')

    opt = raw_input('''
You now need to configure Indico, by editing indico.conf or letting us do it for you.
At this point you can:

    [c]opy the default values in etc/indico.conf.sample to a new etc/indico.conf
    and continue the installation

    [A]bort the installation in order to inspect etc/indico.conf.sample
    and / or to make your own etc/indico.conf

What do you want to do [c/a]? ''')
    if opt in ('c', 'C'):
        shutil.copy(PWD_INDICO_CONF + '.sample', indicoconfpath)
        _replacePrefixInConf(indicoconfpath, prefixDir)
    elif opt in ('', 'a', 'A'):
        print "\nExiting installation..\n"
        sys.exit()
    else:
        print "\nInvalid answer. Exiting installation..\n"
        sys.exit()

    return dict((dirName, os.path.join(prefixDir, dirName))
                for dirName in ['bin','doc','etc','htdocs','tmp','log','cache'])


def indico_post_install(targetDirs, sourceDirs, makacconfig_base_dir, package_dir, uid=None, gid=None):
    print "Creating directories for resources... ",
    # Create the directories where the resources will be installed
    createDirs(targetDirs)
    print "done!"

    # target configuration file (may exist or not)
    newConf = os.path.join(targetDirs['etc'],'indico.conf')
    # source configuration file (package)
    sourceConf = os.path.join(sourceDirs['etc'], 'indico.conf.sample')

    # if there is a source config
    if os.path.exists(sourceConf) and not os.path.exists(newConf):
        # just copy if there is no config yet
        shutil.copy(sourceConf, newConf)

    # copy the logging config
    fpath = os.path.join(targetDirs['etc'], 'logging.conf')
    if not os.path.exists(fpath):
        shutil.copy(fpath + '.sample', fpath)

    #we delete an existing vars.js.tpl.tmp
    tmp_dir = targetDirs['tmp']

    varsJsTplTmpPath = os.path.join(tmp_dir, 'vars.js.tpl.tmp')
    if os.path.exists(varsJsTplTmpPath):
        print 'Old vars.js.tpl.tmp found at: %s. Removing' % varsJsTplTmpPath
        os.remove(varsJsTplTmpPath)

    # find the apache user/group
    user, group = _findApacheUserGroup(uid, gid)

    # check permissions
    _checkDirPermissions(targetDirs, accessuser=user, accessgroup=group)
    # check that mod_python is installed
    _checkModPythonIsInstalled()

    print """

Congratulations!
Indico has been installed correctly.

    indico.conf:      {conf}

    BinDir:           {bin}
    ConfigurationDir: {etc}
    HtdocsDir:        {htdocs}

To run Indico, you need to set the INDICO_CONFIG environment variable
to {conf} or add `indico_config: {conf}` to /etc/indico.yaml
or ~/.indico.yaml (not recommended for production):

For information on how to configure Apache HTTPD, take a look at:

http://indico.readthedocs.org/en/latest/installation/#configuring-the-web-server


Please do not forget to start the Celery worker in order to use background tasks
such as event reminders and periodic cleanups. You can run it using this command:
$ indico celery worker -B
""".format(conf='{}/indico.conf'.format(targetDirs['etc']), etc=targetDirs['etc'], bin=targetDirs['bin'],
           htdocs=targetDirs['htdocs'])