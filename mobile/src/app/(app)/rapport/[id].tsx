import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import MapView, { Marker, Polygon, Polyline, type LatLng } from 'react-native-maps';

import { Badge, Button, Card, colors, fmtDateTime, fmtTime, Label, Muted, Row } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { formatDistance } from '@/lib/geo';
import { flush, outbox } from '@/lib/outbox';
import type { RoundReport } from '@/lib/types';

const toLatLng = ([lon, lat]: number[]): LatLng => ({ latitude: lat, longitude: lon });

export default function Rapport() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [report, setReport] = useState<RoundReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const map = useRef<MapView>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await flush(); // la fin de ronde vient peut-être juste d'être enregistrée
      setReport(await api<RoundReport>(`/rounds/${id}/report`));
    } catch (e) {
      const pending = outbox.get().ops.some((o) => o.path.includes(String(id)));
      setError(
        pending || (e instanceof ApiError && e.status === 404)
          ? 'La ronde n’est pas encore arrivée au serveur (pas de réseau ?). Le rapport sera disponible après l’envoi.'
          : e instanceof Error
            ? e.message
            : String(e),
      );
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !report) {
    return (
      <View style={[s.page, { flex: 1, justifyContent: 'center' }]}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }
  if (!report) {
    return (
      <View style={s.page}>
        <Card>
          <Text style={{ color: colors.text }}>{error}</Text>
          <Button title="Réessayer" onPress={load} />
        </Card>
      </View>
    );
  }

  const track = report.track?.coordinates.map(toLatLng) ?? [];
  const perimeter = report.site.perimeter?.coordinates[0]?.map(toLatLng) ?? [];
  const cps = report.checkpoints.filter((c) => c.location);
  const allPoints = [...track, ...perimeter, ...cps.map((c) => ({ latitude: c.location!.lat, longitude: c.location!.lon }))];
  const fit = () =>
    allPoints.length &&
    map.current?.fitToCoordinates(allPoints, { edgePadding: { top: 40, bottom: 40, left: 40, right: 40 }, animated: false });

  const pct = report.completion_pct;
  const dur = report.duration_min;
  const durTone = dur == null ? 'muted' : dur < report.expected_duration_min * 0.4 || dur > report.expected_duration_min * 2 ? 'warning' : 'success';

  return (
    <ScrollView contentContainerStyle={s.page}>
      <View>
        <Text style={s.title}>{report.template.name}</Text>
        <Muted>
          {report.site.name} · {report.agent.full_name} · {fmtDateTime(report.round.started_at)}
        </Muted>
      </View>

      <View style={s.mapWrap}>
        <MapView ref={map} style={StyleSheet.absoluteFill} onMapReady={fit} mapType="standard" userInterfaceStyle="dark">
          {perimeter.length > 2 && (
            <Polygon coordinates={perimeter} strokeColor={colors.primary} fillColor="rgba(59,130,246,0.12)" strokeWidth={2} />
          )}
          {track.length > 1 && <Polyline coordinates={track} strokeColor="#facc15" strokeWidth={4} />}
          {cps.map((c) => (
            <Marker
              key={c.checkpoint_id}
              coordinate={{ latitude: c.location!.lat, longitude: c.location!.lon }}
              title={`${c.order_index}. ${c.name}`}
              description={c.scanned ? `Contrôlé à ${fmtTime(c.scanned_at)} · ${formatDistance(c.distance_m)}` : 'Non contrôlé'}
              pinColor={!c.scanned ? 'red' : c.is_valid ? 'green' : 'orange'}
            />
          ))}
        </MapView>
      </View>
      <Row style={{ flexWrap: 'wrap' }}>
        <Badge label="— trajet GPS" tone="warning" />
        <Badge label="● contrôlé" tone="success" />
        <Badge label="● scan à distance" tone="warning" />
        <Badge label="● manqué" tone="danger" />
      </Row>

      <Row>
        <Tile label="Points" value={`${Math.round(pct)} %`} tone={pct === 100 ? colors.success : colors.warning} />
        <Tile
          label="Durée"
          value={dur == null ? '—' : `${Math.round(dur)} min`}
          sub={`prévu ${report.expected_duration_min}`}
          tone={durTone === 'success' ? colors.success : durTone === 'warning' ? colors.warning : colors.muted}
        />
        <Tile label="Distance" value={formatDistance(report.distance_walked_m)} tone={colors.primary} />
      </Row>

      <Card>
        <Label>Alertes</Label>
        {report.flags.length ? (
          report.flags.map((f) => (
            <Row key={f}>
              <Text style={{ color: colors.warning }}>⚠</Text>
              <Text style={{ color: colors.text, flex: 1 }}>{f}</Text>
            </Row>
          ))
        ) : (
          <Row>
            <Text style={{ color: colors.success }}>✓</Text>
            <Text style={{ color: colors.text }}>Ronde conforme</Text>
          </Row>
        )}
      </Card>

      <Card>
        <Label>Points de contrôle</Label>
        {report.checkpoints.map((c) => (
          <Row key={c.checkpoint_id} style={{ justifyContent: 'space-between' }}>
            <Text style={{ color: colors.text, flex: 1 }}>
              {c.order_index}. {c.name}
            </Text>
            {c.scanned ? (
              <Muted>
                {fmtTime(c.scanned_at)} · +{Math.round(c.minutes_since_start ?? 0)} min · {formatDistance(c.distance_m)}
              </Muted>
            ) : (
              <Badge label="manqué" tone="danger" />
            )}
          </Row>
        ))}
        {report.round.comment ? <Muted>Commentaire : {report.round.comment}</Muted> : null}
      </Card>
    </ScrollView>
  );
}

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone: string }) {
  return (
    <View style={[s.tile, { borderColor: tone }]}>
      <Text style={s.tileLabel}>{label}</Text>
      <Text style={[s.tileValue, { color: tone }]}>{value}</Text>
      {sub ? <Text style={s.tileLabel}>{sub}</Text> : null}
    </View>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 14, paddingBottom: 40 },
  title: { color: colors.text, fontSize: 22, fontWeight: '900' },
  mapWrap: { height: 320, borderRadius: 16, overflow: 'hidden', borderWidth: 1, borderColor: colors.border },
  tile: { flex: 1, backgroundColor: colors.card, borderRadius: 14, borderWidth: 1, padding: 12, gap: 2 },
  tileLabel: { color: colors.muted, fontSize: 11, fontWeight: '700' },
  tileValue: { fontSize: 22, fontWeight: '900' },
});
