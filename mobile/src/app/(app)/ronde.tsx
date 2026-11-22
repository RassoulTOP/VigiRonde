import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { SyncBar } from '@/components/SyncBar';
import { Badge, Button, Card, colors, fmtDuration, fmtTime, Label, Muted, Row } from '@/components/ui';
import { formatDistance } from '@/lib/geo';
import { useSession } from '@/lib/session';

export default function Ronde() {
  const session = useSession();
  const { activeRound, templates, site } = session;
  const [manual, setManual] = useState(false);
  const [code, setCode] = useState('');
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(t);
  }, []);

  if (!activeRound) {
    return (
      <View style={s.page}>
        <Card>
          <Text style={{ color: colors.text }}>Aucune ronde en cours.</Text>
          <Button title="Retour" onPress={() => router.back()} />
        </Card>
      </View>
    );
  }

  const tpl = templates.find((t) => t.id === activeRound.templateId);
  const byId = new Map(site?.checkpoints.map((c) => [c.id, c]));
  const points = (tpl?.checkpoint_ids ?? []).map((id) => byId.get(id)).filter((c) => !!c);
  const scans = new Map(activeRound.scans.map((sc) => [sc.checkpoint_id, sc]));
  const next = points.find((c) => !scans.has(c.id));
  const done = points.filter((c) => scans.has(c.id)).length;
  const elapsedMin = (now - new Date(activeRound.startedAt).getTime()) / 60000;
  const overtime = tpl && elapsedMin > tpl.expected_duration_min * 2;

  async function submitManual() {
    const res = await session.scan(code, 'manuel');
    if (!res.ok) {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      Alert.alert('Code refusé', res.message);
      return;
    }
    void Haptics.notificationAsync(res.valid ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Warning);
    setCode('');
    setManual(false);
    if (!res.valid) Alert.alert('Point enregistré', `Vous semblez être à ${formatDistance(res.distance)} du point : ce passage sera signalé.`);
  }

  async function finish(interrupted: boolean) {
    setBusy(true);
    try {
      const id = await session.endRound({ interrupted, comment });
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.replace(`/rapport/${id}`);
    } catch (e) {
      Alert.alert('Erreur', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function askFinish() {
    const missing = points.length - done;
    if (missing === 0) return void finish(false);
    Alert.alert(
      `${missing} point(s) non contrôlé(s)`,
      'Ils apparaîtront comme manqués dans le rapport. Ajoutez un commentaire pour expliquer pourquoi.',
      [
        { text: 'Continuer la ronde', style: 'cancel' },
        { text: 'Interrompre la ronde', style: 'destructive', onPress: () => void finish(true) },
        { text: 'Terminer quand même', onPress: () => void finish(false) },
      ],
    );
  }

  return (
    <ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
      <SyncBar />
      <Card>
        <Row style={{ justifyContent: 'space-between' }}>
          <Label>{tpl?.name ?? 'Ronde'}</Label>
          <Badge label={`${done}/${points.length}`} tone={done === points.length ? 'success' : 'primary'} />
        </Row>
        <Text style={s.big}>{fmtDuration(activeRound.startedAt, now)}</Text>
        <Muted>
          Commencée à {fmtTime(activeRound.startedAt)} · durée prévue {tpl?.expected_duration_min ?? '?'} min
        </Muted>
        {overtime && <Badge label="Ronde anormalement longue" tone="warning" />}
        {next ? (
          <View style={s.next}>
            <Label>Prochain point</Label>
            <Text style={s.nextName}>
              {next.order_index}. {next.name}
            </Text>
            {next.instructions ? <Muted>{next.instructions}</Muted> : null}
          </View>
        ) : (
          <Badge label="Tous les points sont contrôlés ✓" tone="success" />
        )}
        <Button title="Scanner le QR code" icon="▣" big onPress={() => router.push('/scanner')} />
        {manual ? (
          <Row>
            <TextInput
              style={[s.input, { flex: 1 }]}
              value={code}
              onChangeText={setCode}
              placeholder="Code du point (ex. VR-…)"
              placeholderTextColor={colors.muted}
              autoCapitalize="characters"
              autoFocus
              onSubmitEditing={submitManual}
            />
            <Button title="OK" onPress={submitManual} disabled={!code.trim()} />
          </Row>
        ) : (
          <Button title="QR illisible ? Saisir le code" variant="ghost" onPress={() => setManual(true)} />
        )}
      </Card>

      <Card>
        <Label>Parcours</Label>
        {points.map((c) => {
          const sc = scans.get(c.id);
          const isNext = c.id === next?.id;
          return (
            <View key={c.id} style={[s.point, isNext && { borderColor: colors.primary }]}>
              <View
                style={[
                  s.dot,
                  { backgroundColor: sc ? (sc.is_valid ? colors.success : colors.warning) : isNext ? colors.primary : colors.border },
                ]}
              >
                <Text style={s.dotText}>{sc ? (sc.is_valid ? '✓' : '!') : c.order_index}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontWeight: '700' }}>{c.name}</Text>
                {sc ? (
                  <Muted>
                    {fmtTime(sc.scanned_at)} · {formatDistance(sc.distance_m)} du point
                    {sc.method === 'manuel' ? ' · saisie manuelle' : ''}
                    {!sc.is_valid ? ' · trop loin, sera signalé' : ''}
                  </Muted>
                ) : (
                  <Muted>À contrôler</Muted>
                )}
              </View>
            </View>
          );
        })}
      </Card>

      <Card>
        <Label>Commentaire de fin de ronde</Label>
        <TextInput
          style={[s.input, { minHeight: 70, textAlignVertical: 'top' }]}
          value={comment}
          onChangeText={setComment}
          placeholder="RAS, ou ce qui a empêché de contrôler un point… (dictée vocale possible avec le micro du clavier)"
          placeholderTextColor={colors.muted}
          multiline
        />
        <Button title="Signaler un incident" icon="⚠️" variant="danger" onPress={() => router.push('/incident')} />
        <Button title="Terminer la ronde" variant="success" onPress={askFinish} loading={busy} />
      </Card>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 14, paddingBottom: 40 },
  big: { color: colors.text, fontSize: 36, fontWeight: '900', fontVariant: ['tabular-nums'] },
  next: { backgroundColor: colors.cardAlt, borderRadius: 12, padding: 12, gap: 4 },
  nextName: { color: colors.text, fontSize: 18, fontWeight: '800' },
  input: {
    backgroundColor: colors.cardAlt,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    color: colors.text,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 15,
  },
  point: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 10,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  dot: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  dotText: { color: '#fff', fontWeight: '800' },
});
