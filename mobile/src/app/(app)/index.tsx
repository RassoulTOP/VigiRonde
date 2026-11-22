import * as Haptics from 'expo-haptics';
import { router, type Href } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { SyncBar } from '@/components/SyncBar';
import { Badge, Button, Card, colors, fmtDateTime, fmtDuration, fmtTime, Label, Muted, Row, Title } from '@/components/ui';
import { usePoste } from '@/lib/poste';
import { useSession } from '@/lib/session';
import { isTracking, onFix } from '@/lib/tracking';
import { useOutbox } from '@/lib/useOutbox';

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

type TileProps = {
  label: string;
  sub?: string;
  color: string;
  icon: string;
  badge?: number | string | null;
  onPress: () => void;
  disabled?: boolean;
};

function Tile({ label, sub, color, icon, badge, onPress, disabled }: TileProps) {
  return (
    <Pressable
      onPress={() => {
        void Haptics.selectionAsync();
        onPress();
      }}
      disabled={disabled}
      style={({ pressed }) => [s.tile, { backgroundColor: color, opacity: disabled ? 0.4 : pressed ? 0.8 : 1 }]}
    >
      <Text style={s.tileIcon}>{icon}</Text>
      <Text style={s.tileLabel} numberOfLines={1} adjustsFontSizeToFit>
        {label}
      </Text>
      {sub ? (
        <Text style={s.tileSub} numberOfLines={1}>
          {sub}
        </Text>
      ) : null}
      {badge ? (
        <View style={s.badge}>
          <Text style={s.badgeText}>{badge}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

export default function Home() {
  const session = useSession();
  const poste = usePoste();
  const { user, shift, site, templates, activeRound, refreshing } = session;
  const { online } = useOutbox();
  const [busy, setBusy] = useState<string | null>(null);
  const now = useNow(15000);
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

  const unread = poste.instructions.filter((i) => !i.acked_at).length;

  const startShift = () =>
    run('start', async () => {
      const { inside, fix } = await session.startShift();
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      if (!fix) Alert.alert('Service commencé', 'Position GPS indisponible : la prise de service sera signalée au superviseur.');
      else if (inside === false)
        Alert.alert('Service commencé hors du site', 'Vous n’êtes pas dans le périmètre du site. Votre superviseur en sera informé.');
      if (unread > 0) {
        Alert.alert(`${unread} consigne(s) à lire`, 'Prenez connaissance des consignes du site avant votre première ronde.', [
          { text: 'Plus tard', style: 'cancel' },
          { text: 'Lire', onPress: () => router.push('/consignes') },
        ]);
      }
    });

  const endShift = () =>
    Alert.alert('Fin de service', 'Confirmer la fin de votre vacation ? Le suivi GPS et le PTI s’arrêteront.', [
      { text: 'Annuler', style: 'cancel' },
      {
        text: 'Terminer',
        style: 'destructive',
        onPress: () =>
          void run('end', async () => {
            if (poste.pause) await poste.endPause();
            await session.endShift();
          }),
      },
    ]);

  const togglePause = () =>
    run('pause', async () => {
      if (poste.pause) await poste.endPause();
      else await poste.startPause();
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    });

  const onDuty = shift?.status === 'en_cours';
  const firstName = user?.full_name.split(' ')[0] ?? '';
  const activeTpl = templates.find((t) => t.id === activeRound?.templateId);
  const scanned = new Set(activeRound?.scans.map((x) => x.checkpoint_id)).size;
  const alertActive = poste.alert && (poste.alert.status === 'active' || poste.alert.status === 'prise_en_charge');
  const go = (href: Href) => () => router.push(href);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['top']}>
      <ScrollView
        contentContainerStyle={s.page}
        refreshControl={
          <RefreshControl
            refreshing={refreshing || poste.syncing}
            onRefresh={() => {
              void session.refresh().catch(() => undefined);
              void poste.sync().catch(() => undefined);
            }}
            tintColor={colors.muted}
          />
        }
      >
        {/* En-tête : site + état réseau, GPS, PTI */}
        <Row style={{ justifyContent: 'space-between' }}>
          <View style={{ flex: 1 }}>
            <Row>
              <View style={[s.dot, { backgroundColor: online ? colors.success : colors.warning }]} />
              <Text style={s.site} numberOfLines={1}>
                {site?.name ?? shift?.site_name ?? 'VigiRonde'}
              </Text>
            </Row>
            <Muted>
              {firstName} · {new Date(now).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })}
            </Muted>
          </View>
          <Pressable onPress={go('/pti')} style={[s.pti, alertActive && { backgroundColor: colors.danger }]}>
            <Text style={{ fontSize: 22 }}>🛡️</Text>
            <Text style={s.ptiText}>{onDuty && poste.ptiEnabled && !poste.pause ? 'PTI actif' : 'PTI'}</Text>
          </Pressable>
        </Row>

        {alertActive && (
          <Pressable onPress={go('/pti')} style={s.alertBanner}>
            <Text style={s.alertText}>
              {poste.alert?.status === 'prise_en_charge'
                ? `Alerte prise en charge par ${poste.alert.handled_by_name ?? 'le PC sécurité'}`
                : poste.alert?.sent
                  ? 'ALERTE ENVOYÉE — en attente de prise en charge'
                  : 'ALERTE EN ATTENTE DE RÉSEAU…'}
            </Text>
          </Pressable>
        )}

        <SyncBar />

        {!onDuty && (
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
                <Button title="Prendre mon service" icon="▶" variant="success" big onPress={startShift} loading={busy === 'start'} />
              </>
            )}
          </Card>
        )}

        {onDuty && (
          <Row style={{ flexWrap: 'wrap' }}>
            <Badge label={`En service depuis ${fmtDuration(shift.actual_start ?? shift.planned_start, now)}`} tone="primary" />
            <Badge
              label={isTracking() ? `GPS${accuracy != null ? ` ±${Math.round(accuracy)} m` : ''}` : 'GPS inactif'}
              tone={isTracking() ? 'success' : 'warning'}
            />
            {shift.start_inside_perimeter === false && <Badge label="Prise de service hors site" tone="danger" />}
            {poste.pause && <Badge label={`En pause · ${fmtDuration(poste.pause.startedAt, now)}`} tone="warning" />}
          </Row>
        )}

        {onDuty && activeRound && (
          <Pressable onPress={go('/ronde')} style={s.round}>
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={s.roundTitle}>{activeTpl?.name ?? 'Ronde'} en cours</Text>
              <Muted>
                {scanned}/{activeTpl?.checkpoint_ids.length ?? '?'} points · depuis {fmtDuration(activeRound.startedAt, now)}
              </Muted>
              <View style={s.progress}>
                <View
                  style={[s.progressFill, { width: `${activeTpl ? (100 * scanned) / activeTpl.checkpoint_ids.length : 0}%` }]}
                />
              </View>
            </View>
            <Text style={{ color: colors.primary, fontSize: 28 }}>›</Text>
          </Pressable>
        )}

        {/* Tuiles */}
        <View style={s.grid}>
          {onDuty ? (
            <Tile label="Fin de service" icon="⏹" color="#16a34a" onPress={endShift} disabled={busy === 'end'} />
          ) : (
            <Tile label="Historique" icon="🗂" color="#16a34a" onPress={go('/historique')} />
          )}
          <Tile
            label="Rondes"
            icon="🧭"
            color="#2563eb"
            sub={activeRound ? 'ronde en cours' : `${templates.length} parcours`}
            onPress={go(activeRound ? '/ronde' : '/rondes')}
            disabled={!onDuty}
          />
          <Tile label="Rapports" icon="📋" color="#ea580c" sub={`${poste.reportTemplates.length} modèles`} onPress={go('/rapports')} disabled={!shift || shift.status === 'terminee'} />
          <Tile label="Main courante" icon="📓" color="#4338ca" onPress={go('/journal')} disabled={!onDuty} />
          <Tile label="Évt simple" icon="⚡" color="#dc2626" sub="en un geste" onPress={go('/evenement')} disabled={!onDuty} />
          <Tile label="Consignes" icon="📌" color="#9333ea" badge={unread || null} onPress={go('/consignes')} disabled={!shift || shift.status === 'terminee'} />
          <Tile
            label={poste.pause ? 'Fin de pause' : 'Début pause'}
            icon="☕"
            color="#92400e"
            sub={poste.pause ? fmtDuration(poste.pause.startedAt, now) : undefined}
            onPress={togglePause}
            disabled={!onDuty || busy === 'pause' || !!activeRound}
          />
          <Tile label="Clés" icon="🔑" color="#db2777" badge={poste.keys.filter((k) => k.is_out).length || null} onPress={go('/clefs')} disabled={!onDuty} />
          <Tile label="Visiteurs" icon="🪪" color="#0d9488" badge={poste.visits.length || null} onPress={go('/visiteurs')} disabled={!onDuty} />
          <Tile label="SOS / PTI" icon="🆘" color="#7f1d1d" onPress={go('/pti')} />
        </View>

        {/* Rapports fréquents */}
        {shift && shift.status !== 'terminee' && poste.reportTemplates.length > 0 && (
          <Card>
            <Row style={{ justifyContent: 'space-between' }}>
              <Label>Rapports fréquents</Label>
              <Pressable onPress={go('/rapports')}>
                <Text style={{ color: colors.primary, fontWeight: '700' }}>Voir tout</Text>
              </Pressable>
            </Row>
            <Row style={{ justifyContent: 'space-between' }}>
              {poste.reportTemplates.slice(0, 3).map((t) => (
                <Pressable
                  key={t.id}
                  onPress={() => router.push({ pathname: '/incident', params: { template: t.id } })}
                  style={s.quick}
                >
                  <Text style={{ fontSize: 26 }}>{t.icon ?? '📋'}</Text>
                  <Text style={s.quickText} numberOfLines={2}>
                    {t.name}
                  </Text>
                </Pressable>
              ))}
            </Row>
          </Card>
        )}

        <Row style={{ justifyContent: 'space-between', marginTop: 4 }}>
          {onDuty && <Button title="Historique" variant="ghost" onPress={go('/historique')} style={{ flex: 1 }} />}
          <Button
            title="Déconnexion"
            variant="ghost"
            style={{ flex: 1 }}
            onPress={() =>
              Alert.alert('Se déconnecter ?', onDuty ? 'Votre vacation reste en cours.' : undefined, [
                { text: 'Annuler', style: 'cancel' },
                { text: 'Déconnexion', style: 'destructive', onPress: () => void session.logout() },
              ])
            }
          />
        </Row>
        <Muted style={{ textAlign: 'center', fontSize: 11 }}>{user?.email} · VigiRonde</Muted>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 14, paddingBottom: 40 },
  site: { color: colors.text, fontSize: 22, fontWeight: '900', flexShrink: 1 },
  dot: { width: 12, height: 12, borderRadius: 6 },
  pti: {
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  ptiText: { color: colors.text, fontSize: 10, fontWeight: '800' },
  alertBanner: { backgroundColor: colors.danger, borderRadius: 14, padding: 14 },
  alertText: { color: '#fff', fontWeight: '900', textAlign: 'center' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  tile: {
    width: '48.5%',
    minHeight: 92,
    borderRadius: 16,
    padding: 14,
    justifyContent: 'flex-end',
  },
  tileIcon: { fontSize: 24, position: 'absolute', top: 12, left: 14 },
  tileLabel: { color: '#fff', fontSize: 17, fontWeight: '900', textTransform: 'uppercase' },
  tileSub: { color: 'rgba(255,255,255,0.8)', fontSize: 12, fontWeight: '600' },
  badge: {
    position: 'absolute',
    top: 10,
    right: 10,
    minWidth: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  badgeText: { color: '#111827', fontWeight: '900' },
  round: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: colors.cardAlt,
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.primary,
  },
  roundTitle: { color: colors.text, fontSize: 17, fontWeight: '800' },
  progress: { height: 6, backgroundColor: colors.border, borderRadius: 3, overflow: 'hidden', marginTop: 4 },
  progressFill: { height: 6, backgroundColor: colors.success },
  quick: { flex: 1, alignItems: 'center', gap: 6, padding: 8, borderRadius: 12, backgroundColor: colors.cardAlt },
  quickText: { color: colors.text, fontSize: 12, fontWeight: '600', textAlign: 'center' },
});
