import * as Haptics from 'expo-haptics';
import { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { Badge, Button, Card, colors, fmtDateTime, Label, Muted, Row } from '@/components/ui';
import { usePoste } from '@/lib/poste';
import type { SiteKey } from '@/lib/types';

export default function Clefs() {
  const { keys, moveKey } = usePoste();
  const [editing, setEditing] = useState<string | null>(null);
  const [holder, setHolder] = useState('');
  const [company, setCompany] = useState('');

  function open(k: SiteKey) {
    setEditing(k.id);
    setHolder(k.is_out ? (k.holder_name ?? '') : '');
    setCompany(k.is_out ? (k.holder_company ?? '') : '');
  }

  async function confirm(k: SiteKey) {
    if (holder.trim().length < 2) return Alert.alert('Nom requis', 'Indiquez à qui la clé est remise (ou qui la rend).');
    await moveKey(k, k.is_out ? 'retour' : 'sortie', holder.trim(), company.trim() || undefined);
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setEditing(null);
  }

  const out = keys.filter((k) => k.is_out);
  const inside = keys.filter((k) => !k.is_out);

  const render = (k: SiteKey) => (
    <Card key={k.id} style={k.is_out ? { borderColor: '#db2777' } : undefined}>
      <Row style={{ justifyContent: 'space-between' }}>
        <View style={{ flex: 1 }}>
          <Text style={s.label}>🔑 {k.label}</Text>
          <Muted style={{ fontSize: 12 }}>
            {k.location_hint ?? ''} · {k.code}
          </Muted>
        </View>
        <Badge label={k.is_out ? 'Sortie' : 'Au poste'} tone={k.is_out ? 'warning' : 'success'} />
      </Row>
      {k.is_out && (
        <Muted>
          Détenue par {k.holder_name}
          {k.holder_company ? ` (${k.holder_company})` : ''} depuis {fmtDateTime(k.since)}
        </Muted>
      )}
      {editing === k.id ? (
        <View style={{ gap: 8 }}>
          <Label>{k.is_out ? 'Rendue par' : 'Remise à'}</Label>
          <TextInput style={s.input} value={holder} onChangeText={setHolder} placeholder="Nom et prénom" placeholderTextColor={colors.muted} autoFocus />
          <TextInput style={s.input} value={company} onChangeText={setCompany} placeholder="Société (facultatif)" placeholderTextColor={colors.muted} />
          <Row>
            <Button title="Annuler" variant="ghost" onPress={() => setEditing(null)} style={{ flex: 1 }} />
            <Button title={k.is_out ? 'Enregistrer le retour' : 'Remettre la clé'} variant={k.is_out ? 'success' : 'primary'} onPress={() => void confirm(k)} style={{ flex: 2 }} />
          </Row>
        </View>
      ) : (
        <Button title={k.is_out ? 'Retour de la clé' : 'Remettre la clé'} variant="ghost" onPress={() => open(k)} />
      )}
    </Card>
  );

  return (
    <ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
      {out.length > 0 && <Label>Clés sorties ({out.length})</Label>}
      {out.map(render)}
      <Label>Au poste ({inside.length})</Label>
      {inside.map(render)}
      {!keys.length && <Muted>Aucune clé enregistrée pour ce site.</Muted>}
      <Muted style={{ fontSize: 12 }}>Chaque remise et chaque retour sont inscrits au registre et en main courante.</Muted>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 12, paddingBottom: 40 },
  label: { color: colors.text, fontSize: 16, fontWeight: '800' },
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
});
