import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Badge, Card, colors, fmtDateTime, Label, Muted, Row } from '@/components/ui';
import { api } from '@/lib/api';
import { INCIDENT_CATEGORIES, type Incident, type RoundOut } from '@/lib/types';

export default function Historique() {
  const [rounds, setRounds] = useState<RoundOut[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api<RoundOut[]>('/rounds', { query: { limit: 30 } }),
      api<Incident[]>('/incidents', { query: { limit: 20 } }),
    ])
      .then(([r, i]) => {
        if (!alive) return;
        setRounds(r);
        setIncidents(i);
        setError(null);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [reloadKey]);

  const load = () => {
    setLoading(true);
    setReloadKey((k) => k + 1);
  };

  return (
    <ScrollView
      contentContainerStyle={s.page}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={colors.muted} />}
    >
      {error && <Muted>Historique indisponible hors réseau ({error}).</Muted>}
      <Card>
        <Label>Mes dernières rondes</Label>
        {rounds.map((r) => (
          <Pressable key={r.id} onPress={() => router.push(`/rapport/${r.id}`)} style={s.item}>
            <View style={{ flex: 1 }}>
              <Text style={s.itemTitle}>{fmtDateTime(r.started_at)}</Text>
              <Muted>
                {r.scans.length} point(s) scanné(s)
                {r.scans.some((x) => !x.is_valid) ? ' · scan à distance' : ''}
              </Muted>
            </View>
            <Badge
              label={r.status === 'en_cours' ? 'en cours' : r.status === 'interrompue' ? 'interrompue' : 'terminée'}
              tone={r.status === 'terminee' ? 'success' : r.status === 'interrompue' ? 'danger' : 'primary'}
            />
            <Text style={{ color: colors.muted, fontSize: 22 }}>›</Text>
          </Pressable>
        ))}
        {!rounds.length && !loading && <Muted>Aucune ronde.</Muted>}
      </Card>
      <Card>
        <Label>Mes derniers incidents</Label>
        {incidents.map((i) => (
          <Row key={i.id} style={s.item}>
            <View style={{ flex: 1 }}>
              <Text style={s.itemTitle}>{i.title}</Text>
              <Muted>
                {INCIDENT_CATEGORIES[i.category]} · gravité {i.severity} · {fmtDateTime(i.occurred_at)}
                {i.attachments.length ? ` · ${i.attachments.length} photo(s)` : ''}
              </Muted>
            </View>
            <Badge label={i.status.replace('_', ' ')} tone={i.status === 'clos' ? 'success' : 'warning'} />
          </Row>
        ))}
        {!incidents.length && !loading && <Muted>Aucun incident.</Muted>}
      </Card>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 14, paddingBottom: 40 },
  item: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border },
  itemTitle: { color: colors.text, fontWeight: '700' },
});
