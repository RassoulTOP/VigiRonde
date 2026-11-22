import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { SyncBar } from '@/components/SyncBar';
import { Badge, Button, Card, colors, fmtDateTime, fmtDuration, fmtTime, Label, Muted, Row, Title } from '@/components/ui';
import { formatDistance } from '@/lib/geo';
import { useSession } from '@/lib/session';
import { isTracking, onFix } from '@/lib/tracking';

function useNow(intervalMs = 30000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

function useGpsAccuracy() {
  const [acc, setAcc] = useState<number | null>(null);
  useEffect(() => {
    const off = onFix((f) => setAcc(f.coords.accuracy ?? null));
    return () => {
      off();
    };
  }, []);
  return acc;
}

export default function Home() {
  const session = useSession();
  const { user, shift, site, templates, activeRound, lastRoundId, refreshing } = session;
  const [busy, setBusy] = useState<string | null>(null);
  const now = useNow();
  const accuracy = useGpsAccuracy();

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    try {
      await fn();
    } catch (e) {
      Alert.alert('Action impossible', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const startShift = () =>
    run('start', async () => {
      const { inside, fix } = await session.startShift();
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      if (!fix) Alert.alert('Service commencé', 'Position GPS indisponible : la prise de service sera signalée au superviseur.');
      else if (inside === false)
        Alert.alert('Service commencé hors du site', 'Vous n’êtes pas dans le périmètre du site. Votre superviseur en sera informé.');
    });

  const endShift = () =>
    Alert.alert('Fin de service', 'Confirmer la fin de votre vacation ? Le suivi GPS s’arrêtera.', [
      { text: 'Annuler', style: 'cancel' },
      { text: 'Terminer', style: 'destructive', onPress: () => void run('end', session.endShift) },
    ]);

  const startRound = (templateId: string) =>
    run(templateId, async () => {
      await session.startRound(templateId);
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      router.push('/ronde');
    });

  const firstName = user?.full_name.split(' ')[0] ?? '';
  const activeTpl = templates.find((t) => t.id === activeRound?.templateId);
  const scannedIds = new Set(activeRound?.scans.map((s) => s.checkpoint_id));

  return (
    <ScrollView
      contentContainerStyle={s.page}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void session.refresh().catch(() => undefined)} tintColor={colors.muted} />}
    >
      <Row style={{ justifyContent: 'space-between' }}>
        <View>
          <Text style={s.hello}>Bonjour {firstName}</Text>
          <Muted>{new Date(now).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })}</Muted>
        </View>
        {shift?.status === 'en_cours' && (
          <Badge
            label={isTracking() ? `GPS actif${accuracy != null ? ` ±${Math.round(accuracy)} m` : ''}` : 'GPS inactif'}
            tone={isTracking() ? 'success' : 'warning'}
          />
        )}
      </Row>

      <SyncBar />

      {/* ---------- Vacation ---------- */}
      <Card>
        <Label>Ma vacation</Label>
        {!shift || shift.status === 'terminee' ? (
          <>
            <Title>{shift?.status === 'terminee' ? 'Service terminé' : 'Aucune vacation prévue'}</Title>
            <Muted>
              {shift?.status === 'terminee'
                ? `Fin à ${fmtTime(shift.actual_end)}. Bon repos !`
                : 'Rien de prévu dans les 36 prochaines heures. Tirez vers le bas pour actualiser.'}
            </Muted>
          </>
        ) : (
          <>
            <Title>{site?.name ?? shift.site_name}</Title>
            {site?.address ? <Muted>{site.address}</Muted> : null}
            <Muted>
              Prévu {fmtDateTime(shift.planned_start)} → {fmtTime(shift.planned_end)}
            </Muted>
            {shift.status === 'planifiee' ? (
              <Button title="Prendre mon service" icon="▶" variant="success" big onPress={startShift} loading={busy === 'start'} />
            ) : (
              <Row style={{ flexWrap: 'wrap' }}>
                <Badge label={`En service depuis ${fmtDuration(shift.actual_start ?? shift.planned_start, now)}`} tone="primary" />
                {shift.start_inside_perimeter === true && <Badge label="Prise de service sur site" tone="success" />}
                {shift.start_inside_perimeter === false && <Badge label="Prise de service hors site" tone="danger" />}
              </Row>
            )}
          </>
        )}
      </Card>

      {/* ---------- Rondes ---------- */}
      {shift?.status === 'en_cours' && (
        <Card>
          <Label>Rondes</Label>
          {activeRound ? (
            <Pressable onPress={() => router.push('/ronde')} style={s.activeRound}>
              <View style={{ flex: 1, gap: 4 }}>
                <Text style={s.activeTitle}>{activeTpl?.name ?? 'Ronde'} en cours</Text>
                <Muted>
                  {scannedIds.size}/{activeTpl?.checkpoint_ids.length ?? '?'} points · depuis {fmtDuration(activeRound.startedAt, now)}
                </Muted>
                <View style={s.progress}>
                  <View
                    style={[
                      s.progressFill,
                      { width: `${activeTpl ? (100 * scannedIds.size) / activeTpl.checkpoint_ids.length : 0}%` },
                    ]}
                  />
                </View>
              </View>
              <Text style={{ color: colors.primary, fontSize: 28 }}>›</Text>
            </Pressable>
          ) : templates.length ? (
            templates.map((t) => (
              <Button
                key={t.id}
                title={`${t.name} · ${t.checkpoint_ids.length} points · ${t.expected_duration_min} min`}
                icon="🧭"
                onPress={() => startRound(t.id)}
                loading={busy === t.id}
              />
            ))
          ) : (
            <Muted>Aucun parcours défini pour ce site.</Muted>
          )}
          {lastRoundId && !activeRound && (
            <Button title="Rapport de la dernière ronde" variant="ghost" onPress={() => router.push(`/rapport/${lastRoundId}`)} />
          )}
        </Card>
      )}

      {/* ---------- Incident ---------- */}
      {shift && shift.status !== 'terminee' && (
        <Button title="Signaler un incident" icon="⚠️" variant="danger" big onPress={() => router.push('/incident')} />
      )}

      {shift?.status === 'en_cours' && site && (
        <Card>
          <Label>Points de contrôle du site</Label>
          {site.checkpoints.map((c) => (
            <Row key={c.id} style={{ justifyContent: 'space-between' }}>
              <Text style={{ color: colors.text, flex: 1 }}>
                {c.order_index}. {c.name}
              </Text>
              <Muted>{c.code}</Muted>
            </Row>
          ))}
        </Card>
      )}

      {shift?.status === 'en_cours' && (
        <Button title="Fin de service" variant="ghost" onPress={endShift} loading={busy === 'end'} />
      )}

      <Row style={{ justifyContent: 'space-between', marginTop: 8 }}>
        <Button title="Historique" variant="ghost" onPress={() => router.push('/historique')} style={{ flex: 1 }} />
        <Button
          title="Déconnexion"
          variant="ghost"
          style={{ flex: 1 }}
          onPress={() =>
            Alert.alert('Se déconnecter ?', shift?.status === 'en_cours' ? 'Votre vacation reste en cours.' : undefined, [
              { text: 'Annuler', style: 'cancel' },
              { text: 'Déconnexion', style: 'destructive', onPress: () => void session.logout() },
            ])
          }
        />
      </Row>
      <Muted style={{ textAlign: 'center', fontSize: 11 }}>
        {user?.email} · précision scan : {formatDistance(60)} + GPS
      </Muted>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 14, paddingBottom: 40 },
  hello: { color: colors.text, fontSize: 24, fontWeight: '900' },
  activeRound: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: colors.cardAlt,
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.primary,
  },
  activeTitle: { color: colors.text, fontSize: 17, fontWeight: '800' },
  progress: { height: 6, backgroundColor: colors.border, borderRadius: 3, overflow: 'hidden', marginTop: 4 },
  progressFill: { height: 6, backgroundColor: colors.success },
});
