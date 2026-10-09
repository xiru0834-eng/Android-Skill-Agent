import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import safe_probe_upgrade as upgrade


def archive(entries):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as bundle:
        for name,data,kind in entries:
            item=tarfile.TarInfo(name);item.size=len(data)
            if kind=='link':item.type=tarfile.SYMTYPE;item.linkname='../language_connection.xml'
            bundle.addfile(item,io.BytesIO(data) if kind=='file' else None)
    return stream.getvalue()


class SafeProbeUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.name='shared_prefs/recorded_workflows.xml';self.data=b'<map><string name="library">[]</string></map>'
        self.manifest={self.name:hashlib.sha256(self.data).hexdigest()}
        self.blob=archive([(self.name,self.data,'file')])

    def test_archive_content_is_verified_without_extracting(self):
        self.assertEqual(upgrade.validate_archive(self.blob,self.manifest),self.manifest)

    def test_truncated_or_corrupt_archive_is_rejected(self):
        for blob in [b'not tar',self.blob[:140],self.blob[:512]]:
            with self.subTest(size=len(blob)),self.assertRaises(ValueError):upgrade.validate_archive(blob,self.manifest)

    def test_missing_extra_changed_duplicate_and_symlink_are_rejected(self):
        entries=[[],[(self.name,b'changed','file')],[(self.name,self.data,'file'),(self.name,self.data,'file')],
            [(self.name,self.data,'link')],[(self.name,self.data,'file'),('shared_prefs/language_connection.xml',b'no','file')],
            [('../recorded_workflows.xml',self.data,'file')]]
        for entry in entries:
            with self.subTest(entry=[x[0] for x in entry]),self.assertRaises(ValueError):upgrade.validate_archive(archive(entry),self.manifest)

    def test_scope_excludes_connection_tokens_and_unrelated_preferences(self):
        self.assertTrue(upgrade.allowed('files/workflow-journal-abcd.jsonl'))
        self.assertTrue(upgrade.allowed(self.name))
        for name in ['shared_prefs/language_connection.xml','files/api-key.json','files/../workflow.json','/files/workflow.json','shared_prefs/unknown.xml']:
            with self.subTest(name=name):self.assertFalse(upgrade.allowed(name))

    def test_failed_backup_never_calls_install(self):
        with tempfile.TemporaryDirectory() as root,patch.object(upgrade,'backup',side_effect=ValueError('BACKUP_INVALID')),patch.object(upgrade,'adb_bytes') as command:
            apk=Path(root)/'candidate.apk';apk.write_bytes(b'apk')
            with self.assertRaises(ValueError):upgrade.deploy('serial',apk,Path(root)/'evidence',34)
            command.assert_not_called()

    def test_backup_manifest_changes_block_install(self):
        command=Mock(side_effect=AssertionError('install must not happen'))
        with tempfile.TemporaryDirectory() as root,patch.object(upgrade,'backup',return_value=self.manifest),patch.object(upgrade,'device_manifest',return_value={}),patch.object(upgrade,'adb_bytes',command):
            apk=Path(root)/'candidate.apk';apk.write_bytes(b'apk')
            with self.assertRaisesRegex(ValueError,'STATE_CHANGED_BEFORE_INSTALL'):upgrade.deploy('serial',apk,Path(root)/'evidence',34)
            command.assert_not_called()

    def test_large_backup_uses_stdin_not_windows_argument_list(self):
        manifest={**self.manifest,**{'files/workflow-journal-'+str(i)+'.jsonl':hashlib.sha256(b'x').hexdigest() for i in range(900)}}
        blob=archive([(name,self.data if name==self.name else b'x','file') for name in manifest])
        seen=[]
        def device(serial,*args,**kwargs):
            if 'tar' in args:
                self.assertLess(len(args),12)
                self.assertEqual(args[-2:],('-T','-'))
                self.assertEqual(kwargs['input_data'],(''.join(name+'\n' for name in sorted(manifest))).encode())
                seen.append('tar');return b''
            if 'sha256sum' in args:return (hashlib.sha256(blob).hexdigest()+'  archive').encode()
            return blob
        with tempfile.TemporaryDirectory() as root,patch.object(upgrade,'device_manifest',return_value=manifest),patch.object(upgrade,'adb_bytes',side_effect=device):
            self.assertEqual(upgrade.backup('serial',Path(root)/'evidence'),manifest)
        self.assertEqual(seen,['tar'])


if __name__=='__main__':unittest.main()
