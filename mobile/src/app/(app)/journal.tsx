import { useState } from 'react';
import { Alert, FlatList, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';

import { Button, colors, fmtTime, Muted, Row } from '@/components/ui';
import { usePoste } from '@/lib/poste';
import type { JournalKind } from '@/lib/types';

const KIND: Record<JournalKind, { icon: string; color: string }> = {
  service: { icon: '⏱', color: '#16a34a' },
  ronde: { icon: '🧭', color: '#2563eb' },
  rapport: { icon: '📋', color: '#ea580c' },
  evenement: { icon: '⚡', color: '#dc2626' },
  note: { icon: '✍️', color: '#64748b' },
  pause: { icon: '☕', color: '#92400e' },
  clef: { icon: '🔑', color: '#db2777' },
  visiteur: { icon: '🪪', color: '#0d9488' },
  consigne: { icon: '📌', color: '#9333ea' },
  alerte: { icon: '🛡️', color: '#b91c1c' },
};

export default function Journal() {
  const { journal, loadJournal, addJournal } = usePoste();
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      await loadJournal();
    } catch {
      // hors-ligne : on garde la version locale
    } finally {
      setLoading(false);
    }
  }

  async function add() {
    try {
      await addJournal(text.trim(), 'note');
      setText('');
    } catch (e) {
      Alert.alert('Erreur', e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <View style={{ flex: 1 }}>
      <FlatList
        data={journal}
        keyExtractor={(e) => e.id}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={refresh} tintColor={colors.muted} />}
        contentContainerStyle={{ padding: 16, paddingBottom: 24 }}
        ListEmptyComponent={<Muted>Rien pour l’instant. Tirez vers le bas pour actualiser.</Muted>}
        renderItem={({ item, index }) => {
          const k = KIND[item.kind] ?? KIND.note;
          const day = new Date(item.occurred_at).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
          const prevDay = index > 0 ? new Date(journal[index - 1].occurred_at).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' }) : null;
          return (
            <View>
              {day !== prevDay && <Text style={s.day}>{day}</Text>}
              <View style={s.row}>
                <Text style={s.time}>{fmtTime(item.occurred_at)}</Text>
                <View style={[s.dot, { backgroundColor: k.color }]}>
                  <Text style={{ fontSize: 12 }}>{k.icon}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.text}>{item.text}</Text>
                  <Muted style={{ fontSize: 11 }}>
                    {item.pending ? 'en attente d’envoi' : (item.agent_name ?? '')}
                  </Muted>
                </View>
              </View>
            </View>
          );
        }}
      />
      <Row style={s.composer}>
        <TextInput
          style={s.input}
          value={text}
          onChangeText={setText}
          placeholder="Ajouter une note en main courante…"
          placeholderTextColor={colors.muted}
          multiline
        />
        <Button title="Ajouter" onPress={add} disabled={!text.trim()} />
      </Row>
    </View>
  );
}

const s = StyleSheet.create({
  day: { color: colors.muted, fontWeight: '800', textTransform: 'capitalize', marginTop: 10, marginBottom: 6 },
  row: { flexDirection: 'row', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border, alignItems: 'flex-start' },
  time: { color: colors.text, fontWeight: '800', width: 44, fontVariant: ['tabular-nums'], marginTop: 3 },
  dot: { width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  text: { color: colors.text, fontSize: 15 },
  composer: { padding: 12, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.card, alignItems: 'flex-end' },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    backgroundColor: colors.cardAlt,
    borderRadius: 12,
    color: colors.text,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
});
