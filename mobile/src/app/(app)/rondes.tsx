import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text } from 'react-native';

import { Button, Card, colors, Label, Muted, Row } from '@/components/ui';
import { useSession } from '@/lib/session';

export default function Rondes() {
  const session = useSession();
  const { templates, site, activeRound, lastRoundId } = session;
  const [busy, setBusy] = useState<string | null>(null);

  async function start(id: string) {
    setBusy(id);
    try {
      await session.startRound(id);
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      router.replace('/ronde');
    } catch (e) {
      Alert.alert('Impossible de démarrer', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <ScrollView contentContainerStyle={s.page}>
      {activeRound && <Button title="Continuer la ronde en cours" variant="success" big onPress={() => router.replace('/ronde')} />}
      {templates.map((t) => {
        const names = t.checkpoint_ids.map((id) => site?.checkpoints.find((c) => c.id === id)?.name).filter(Boolean);
        return (
          <Card key={t.id}>
            <Text style={s.title}>🧭 {t.name}</Text>
            <Row style={{ flexWrap: 'wrap' }}>
              <Muted>
                {t.checkpoint_ids.length} points · {t.expected_duration_min} min · {t.rounds_per_shift} par vacation
              </Muted>
            </Row>
            <Muted style={{ fontSize: 12 }}>{names.join(' → ')}</Muted>
            <Button title="Démarrer" onPress={() => void start(t.id)} loading={busy === t.id} disabled={!!activeRound} />
          </Card>
        );
      })}
      {!templates.length && <Muted>Aucun parcours défini pour ce site.</Muted>}
      {lastRoundId && <Button title="Rapport de ma dernière ronde" variant="ghost" onPress={() => router.push(`/rapport/${lastRoundId}`)} />}
      <Label>Astuce</Label>
      <Muted>Pendant la ronde, l’ordre des points et la distance à chaque point sont contrôlés automatiquement.</Muted>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 12, paddingBottom: 40 },
  title: { color: colors.text, fontSize: 18, fontWeight: '800' },
});
