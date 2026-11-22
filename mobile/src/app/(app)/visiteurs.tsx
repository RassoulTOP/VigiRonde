import * as Haptics from 'expo-haptics';
import { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { Badge, Button, Card, colors, fmtDuration, fmtTime, Label, Muted, Row } from '@/components/ui';
import { usePoste, type NewVisit } from '@/lib/poste';

const EMPTY: NewVisit = { visitor_name: '', company: '', reason: '', host_name: '', vehicle_plate: '', badge_number: '' };

export default function Visiteurs() {
  const { visits, addVisit, exitVisit } = usePoste();
  const [form, setForm] = useState<NewVisit | null>(null);
  const set = (k: keyof NewVisit) => (v: string) => setForm((f) => (f ? { ...f, [k]: v } : f));

  async function save() {
    if (!form || form.visitor_name.trim().length < 2) return Alert.alert('Nom requis', 'Indiquez le nom du visiteur.');
    await addVisit(form);
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setForm(null);
  }

  return (
    <ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
      {form ? (
        <Card>
          <Label>Nouveau visiteur</Label>
          <TextInput style={s.input} value={form.visitor_name} onChangeText={set('visitor_name')} placeholder="Nom et prénom *" placeholderTextColor={colors.muted} autoFocus />
          <TextInput style={s.input} value={form.company} onChangeText={set('company')} placeholder="Société" placeholderTextColor={colors.muted} />
          <TextInput style={s.input} value={form.reason} onChangeText={set('reason')} placeholder="Motif (livraison, maintenance…)" placeholderTextColor={colors.muted} />
          <TextInput style={s.input} value={form.host_name} onChangeText={set('host_name')} placeholder="Personne visitée" placeholderTextColor={colors.muted} />
          <Row>
            <TextInput style={[s.input, { flex: 1 }]} value={form.vehicle_plate} onChangeText={set('vehicle_plate')} placeholder="Immatriculation" placeholderTextColor={colors.muted} autoCapitalize="characters" />
            <TextInput style={[s.input, { width: 110 }]} value={form.badge_number} onChangeText={set('badge_number')} placeholder="Badge n°" placeholderTextColor={colors.muted} />
          </Row>
          <Row>
            <Button title="Annuler" variant="ghost" onPress={() => setForm(null)} style={{ flex: 1 }} />
            <Button title="Enregistrer l’arrivée" variant="success" onPress={() => void save()} style={{ flex: 2 }} />
          </Row>
        </Card>
      ) : (
        <Button title="Nouveau visiteur" icon="＋" big onPress={() => setForm(EMPTY)} />
      )}

      <Label>Présents sur le site ({visits.length})</Label>
      {visits.map((v) => (
        <Card key={v.id}>
          <Row style={{ justifyContent: 'space-between' }}>
            <View style={{ flex: 1 }}>
              <Text style={s.name}>{v.visitor_name}</Text>
              <Muted>{[v.company, v.reason].filter(Boolean).join(' · ')}</Muted>
            </View>
            {v.badge_number ? <Badge label={`Badge ${v.badge_number}`} tone="primary" /> : null}
          </Row>
          <Row style={{ flexWrap: 'wrap' }}>
            <Muted>
              Arrivé à {fmtTime(v.arrived_at)} · sur site depuis {fmtDuration(v.arrived_at)}
            </Muted>
            {v.vehicle_plate ? <Badge label={`🚗 ${v.vehicle_plate}`} /> : null}
            {v.host_name ? <Muted>· voit {v.host_name}</Muted> : null}
          </Row>
          <Button
            title="Enregistrer le départ"
            variant="ghost"
            onPress={() =>
              Alert.alert('Départ', `${v.visitor_name} quitte le site ?`, [
                { text: 'Annuler', style: 'cancel' },
                { text: 'Confirmer', onPress: () => void exitVisit(v.id) },
              ])
            }
          />
        </Card>
      ))}
      {!visits.length && <Muted>Aucun visiteur sur le site.</Muted>}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 12, paddingBottom: 40 },
  name: { color: colors.text, fontSize: 17, fontWeight: '800' },
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
