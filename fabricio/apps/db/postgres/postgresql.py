import time

from StringIO import StringIO

from fabric import api as fab
from fabric.contrib import files

import fabricio

from fabricio import docker


class PostgresqlContainer(docker.Container):

    postgresql_conf = NotImplemented  # type: str

    pg_hba_conf = NotImplemented  # type: str

    data = NotImplemented  # type: str

    stop_signal = 'INT'

    stop_timeout = 30

    @staticmethod
    def update_config(content, path):
        old_file = StringIO()
        fab.get(remote_path=path, local_path=old_file, use_sudo=True)
        old_content = old_file.getvalue()
        fabricio.run(
            'mv {path_from} {path_to}'.format(
                path_from=path,
                path_to=path + '.backup',
            ),
            sudo=True,
        )
        fab.put(StringIO(content), path, use_sudo=True, mode='0644')
        return content != old_content

    @property
    def initialized(self):
        return files.exists(self.data + '/PG_VERSION', use_sudo=True)

    def init_db(self):
        self.run()
        time.sleep(10)  # wait until all data prepared during first start

    def update(self, force=False, tag=None, registry=None):
        if not self.initialized:
            self.init_db()
            force = True

        main_config_changed = self.update_config(
            content=open(self.postgresql_conf).read(),
            path=self.data + '/postgresql.conf',
        )
        hba_config_changed = self.update_config(
            content=open(self.pg_hba_conf).read(),
            path=self.data + '/pg_hba.conf',
        )
        force = force or main_config_changed
        updated = super(PostgresqlContainer, self).update(
            force=force,
            tag=tag,
            registry=registry,
        )
        if not updated and hba_config_changed:
            self.signal('HUP')  # reload configs
        return updated

    def revert(self):
        main_conf = self.data + '/postgresql.conf'
        hba_conf = self.data + '/pg_hba.conf'
        fabricio.run(
            'mv {path_from} {path_to}'.format(
                path_from=main_conf + '.backup',
                path_to=main_conf,
            ),
            ignore_errors=True,
            sudo=True,
        )
        fabricio.run(
            'mv {path_from} {path_to}'.format(
                path_from=hba_conf + '.backup',
                path_to=hba_conf,
            ),
            ignore_errors=True,
            sudo=True,
        )
        super(PostgresqlContainer, self).revert()

    def backup(self, dst='', username='postgres'):
        return  # TODO backup arguments should be provided to __init__
        self.execute('psql --username {username} --command "{command};"'.format(
            username=username,
            command="SELECT pg_start_backup('backup')",
        ))
        try:
            command = 'tar --create --exclude postmaster.pid {src} | gzip > {dst}'
            fabricio.run(
                command.format(src=self.data, dst=dst),
                sudo=True,
            )
        finally:
            self.execute('psql --username {username} --command "{command};"'.format(
                username=username,
                command="SELECT pg_stop_backup()",
            ))

    def restore(self, src=''):
        return  # TODO restore arguments should be provided to __init__
        self.stop()
        try:
            command = 'gzip --decompress < {src} | tar --extract --directory {dst}'
            fabricio.run(
                command.format(src=src, dst=self.data),
                sudo=True,
            )
        finally:
            self.start()
