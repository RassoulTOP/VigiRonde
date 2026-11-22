import { Pressable, StyleSheet, Text, View } from 'react-native';

import { dismissFailed, flush } from '@/lib/outbox';
import { useOutbox } from '@/lib/useOutbox';

import { colors, fmtTime } from './ui';

/** Bandeau d'état de la synchronisation : l'agent sait toujours si ses données sont parties. */
export function SyncBar() {
  const { ops, positions, failed, syncing, online, lastSyncAt } = useOutbox();
  const pending = ops.length;

  let tone = colors.success;
  let text = lastSyncAt ? `Tout est envoyé · ${fmtTime(lastSyncAt)}` : 'Synchronisé';
  if (!online) {
    tone = colors.warning;
    text = `Hors réseau · ${pending} action(s) et ${positions.length} point(s) GPS en attente`;
  } else if (syncing) {
    tone = colors.primary;
    text = 'Envoi en cours…';
  } else if (pending || positions.length) {
    tone = colors.primary;
    text = `${pending} action(s) · ${positions.length} point(s) GPS à envoyer`;
  }

  return (
    <View style={{ gap: 6 }}>
      <Pressable onPress={() => void flush()} style={[s.bar, { borderColor: tone }]}>
        <View style={[s.dot, { backgroundColor: tone }]} />
        <Text style={s.text}>{text}</Text>
        {(pending > 0 || positions.length > 0) && <Text style={[s.text, { color: tone }]}>Réessayer</Text>}
      </Pressable>
      {failed.map((f) => (
        <Pressable key={f.id} onPress={() => void dismissFailed(f.id)} style={[s.bar, { borderColor: colors.danger }]}>
          <View style={[s.dot, { backgroundColor: colors.danger }]} />
          <Text style={[s.text, { flex: 1 }]}>
            Refusé : {f.label} — {f.lastError} <Text style={{ color: colors.muted }}>(toucher pour masquer)</Text>
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: colors.card,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  text: { color: colors.text, fontSize: 13, flexShrink: 1 },
});
