import * as Haptics from 'expo-haptics';
import { useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { Badge, Button, Card, colors, fmtTime, Label, Muted, Row } from '@/components/ui';
import { usePoste } from '@/lib/poste';
import { useSession } from '@/lib/session';

const DELAYS = [
  { s: 30, label: '30 s (démo)' },
  { s: 60, label: '1 min' },
  { s: 120, label: '2 min' },
  { s: 300, label: '5 min' },
];

const KIND_LABEL = { sos: 'SOS', immobilite: 'Immobilité', chute: 'Chute', test: 'Test' } as const;

export default function Pti() {
  const { shift } = useSession();
  const { alert, raiseAlert, cancelAlert, refreshAlert, ptiEnabled, ptiDelaySec, setPti, pause } = usePoste();
  const [sending, setSending] = useState(false);
  const active = alert && (alert.status === 'active' || alert.status === 'prise_en_charge');

  // Suivi de la prise en charge par le PC sécurité
  useEffect(() => {
    if (!active) return;
    void refreshAlert();
    const t = setInterval(() => void refreshAlert(), 8000);
    return () => clearInterval(t);
  }, [active, refreshAlert]);

  async function sos() {
    setSending(true);
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    try {
      await raiseAlert('sos');
    } finally {
      setSending(false);
    }
  }

  async function test() {
    const a = await raiseAlert('test');
    Alert.alert(
      'Test du PTI',
      a.sent ? 'Test réussi : l’alerte est bien arrivée au serveur et a été notée en main courante.' : 'Pas de réseau : le test sera envoyé dès que possible.',
    );
  }

  return (
    <ScrollView contentContainerStyle={s.page}>
      {active ? (
        <Card style={{ borderColor: colors.danger, backgroundColor: '#450a0a' }}>
          <Badge label={`Alerte ${KIND_LABEL[alert.kind]} · ${fmtTime(alert.triggered_at)}`} tone="danger" />
          <Text style={s.alertTitle}>
            {alert.status === 'prise_en_charge'
              ? `Prise en charge par ${alert.handled_by_name ?? 'le PC sécurité'}`
              : alert.sent
                ? 'Alerte reçue — le PC sécurité est prévenu'
                : 'En attente de réseau… nouvel essai automatique'}
          </Text>
          <Muted>Restez en sécurité. Votre position est transmise avec l’alerte.</Muted>
          <Button
            title="Fausse alerte — annuler"
            variant="ghost"
            onPress={() =>
              Alert.alert('Annuler l’alerte ?', 'Confirmez que tout va bien.', [
                { text: 'Non', style: 'cancel' },
                { text: 'Tout va bien', onPress: () => void cancelAlert() },
              ])
            }
          />
        </Card>
      ) : (
        <View style={{ alignItems: 'center', gap: 10, paddingVertical: 10 }}>
          <Pressable
            onLongPress={() => void sos()}
            delayLongPress={1500}
            disabled={sending}
            style={({ pressed }) => [s.sos, pressed && { transform: [{ scale: 0.95 }], backgroundColor: '#991b1b' }]}
          >
            <Text style={s.sosText}>SOS</Text>
            <Text style={s.sosSub}>{sending ? 'Envoi…' : 'appui long 2 s'}</Text>
          </Pressable>
          <Muted style={{ textAlign: 'center' }}>Envoie immédiatement une alerte au PC sécurité avec votre position.</Muted>
        </View>
      )}

      <Card>
        <Row style={{ justifyContent: 'space-between' }}>
          <View style={{ flex: 1 }}>
            <Text style={s.h}>Surveillance automatique</Text>
            <Muted>Pré-alarme en cas de chute ou d’immobilité prolongée pendant le service.</Muted>
          </View>
          <Switch value={ptiEnabled} onValueChange={(v) => setPti({ enabled: v })} />
        </Row>
        <Label>Délai d’immobilité</Label>
        <Row>
          {DELAYS.map((d) => (
            <Pressable key={d.s} onPress={() => setPti({ delaySec: d.s })} style={[s.chip, ptiDelaySec === d.s && s.chipOn]}>
              <Text style={[s.chipText, ptiDelaySec === d.s && { color: '#fff' }]}>{d.label}</Text>
            </Pressable>
          ))}
        </Row>
        <Muted style={{ fontSize: 12 }}>
          {shift?.status !== 'en_cours'
            ? 'Inactive : la surveillance démarre avec la prise de service.'
            : pause
              ? 'Suspendue pendant la pause.'
              : ptiEnabled
                ? 'Active. Gardez le téléphone sur vous, appli ouverte.'
                : 'Désactivée.'}
        </Muted>
      </Card>

      <Button title="Tester le PTI" icon="🧪" variant="ghost" onPress={() => void test()} />
      <Muted style={{ fontSize: 11 }}>
        Version de démonstration : dans Expo Go la surveillance ne fonctionne qu’appli ouverte. Un dispositif DATI
        professionnel doit être certifié et fonctionner écran verrouillé (version installée de l’appli).
      </Muted>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 14, paddingBottom: 40 },
  sos: {
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: colors.danger,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 8,
    borderColor: '#fecaca33',
  },
  sosText: { color: '#fff', fontSize: 52, fontWeight: '900', letterSpacing: 2 },
  sosSub: { color: '#fee2e2', fontSize: 13 },
  alertTitle: { color: '#fff', fontSize: 20, fontWeight: '900' },
  h: { color: colors.text, fontSize: 16, fontWeight: '800' },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7 },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text, fontSize: 13, fontWeight: '700' },
});
