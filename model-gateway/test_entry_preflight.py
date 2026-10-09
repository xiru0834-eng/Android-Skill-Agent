import unittest
import xml.etree.ElementTree as ET
import entry_preflight
from entry_preflight import adjudicate


class EntryPreflightTests(unittest.TestCase):
    def complete(self):
        return dict(deviceState='device',installedVersion=34,apkMatches=True,serviceBound=True,
                    permissionEnabled=True,locked=False,executionStatus='SUCCEEDED',recording=False,applicationServiceReady=True)

    def test_platform_binding_is_not_enough_if_application_reports_disconnected(self):
        value=self.complete();value['applicationServiceReady']=False
        self.assertIn('APPLICATION_SERVICE_NOT_READY',adjudicate(value)['reasons'])

    def test_home_service_evidence_is_bilingual_unique_and_exact(self):
        for text in ('● 无障碍服务已连接','● Accessibility connected'):
            with self.subTest(text=text):
                ui=ET.fromstring('<hierarchy><node resource-id="edu.sydney.probe:id/homeService"/></hierarchy>')
                ui[0].set('text',text)
                self.assertIs(entry_preflight.application_service_state(ui),True)
        for text in ('○ 无障碍服务未连接 · 请在设置中开启','○ Accessibility disconnected · Enable it in Settings'):
            ui=ET.fromstring('<hierarchy><node resource-id="edu.sydney.probe:id/homeService"/></hierarchy>')
            ui[0].set('text',text)
            self.assertIs(entry_preflight.application_service_state(ui),False)
        for raw in ('<hierarchy/>','<hierarchy><node resource-id="edu.sydney.probe:id/homeService" text="unknown"/></hierarchy>',
                    '<hierarchy><node resource-id="edu.sydney.probe:id/homeService" text="● Accessibility connected"/><node resource-id="edu.sydney.probe:id/homeService" text="○ Accessibility disconnected · Enable it in Settings"/></hierarchy>'):
            self.assertIsNone(entry_preflight.application_service_state(ET.fromstring(raw)))

    def test_every_required_field_and_type_is_checked(self):
        good=self.complete()
        self.assertEqual(adjudicate(good)['status'],'READY')
        for key in good:
            with self.subTest(key=key):
                bad=good.copy();bad.pop(key)
                self.assertEqual(adjudicate(bad)['status'],'BLOCKED')
        bad=self.complete();bad['installedVersion']=True
        self.assertEqual(adjudicate(bad)['status'],'BLOCKED')

    def test_authorized_but_unbound_cannot_start_execution(self):
        value=self.complete();value['serviceBound']=False
        self.assertIn('SERVICE_NOT_BOUND',adjudicate(value)['reasons'])
        for key,value in [('deviceState','unauthorized'),('deviceState','missing'),('apkMatches',False),
                          ('locked',True),('recording',True),('executionStatus','RUNNING')]:
            bad=self.complete();bad[key]=value
            self.assertEqual(adjudicate(bad)['status'],'BLOCKED')

    def test_preview_only_does_not_infer_execution_readiness(self):
        value=self.complete();value['serviceBound']=False
        result=adjudicate(value,execution=False)
        self.assertEqual(result['status'],'PREVIEW_ONLY')
        self.assertFalse(result['executionReady'])


if __name__=='__main__':unittest.main()
