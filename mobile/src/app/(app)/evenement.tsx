import * as Haptics from 'expo-haptics';
import { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { Button, colors, Label, Muted, Row } from '@/components/ui';
import { usePoste } from '@/lib/poste';

const FALLBACK = ['RAS', 'Ouverture du site', 'Fermeture du site', 'Livraison réceptionnée', 'Alarme acquittée', 'Appel du client'];

export default function Evenement() {
  const { quickEvents, addJournal } = usePoste();
  const [done, setDone] = useState<string[]>([]);
  const [custom, setCustom] = useState('');
  const events = quickEvents.length ? quickEvents : FALLBACK.map((text) => ({ icon: '•', text }));

  async function log(text: string) {
    try {
      await addJournal(text, 'evenement');
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setDone((d) => [`${new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })} · ${text}`, ...d]);
    } catch (e) {
      Alert.alert('Erreur', e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
      <Muted>Un geste = une ligne horodatée et géolocalisée dans la main courante.</Muted>
      <View style={s.grid}>
        {events.map((e) => (
          <Pressable key={e.text} onPress={() => void log(e.text)} style={({ pressed }) => [s.btn, pressed && { backgroundColor: colors.primaryDark }]}>
            <Text style={{ fontSize: 24 }}>{e.icon}</Text>
            <Text style={s.btnText}>{e.text}</Text>
          </Pressable>
        ))}
      </View>
      <Label>Autre évènement</Label>
      <Row>
        <TextInput
          style={s.input}
          value={custom}
          onChangeText={setCustom}
          placeholder="Ex. Passage de la ronde du client"
          placeholderTextColor={colors.muted}
          onSubmitEditing={() => custom.trim() && void log(custom.trim()).then(() => setCustom(''))}
        />
        <Button title="OK" onPress={() => void log(custom.trim()).then(() => setCustom(''))} disabled={!custom.trim()} />
      </Row>
      {done.length > 0 && (
        <View style={{ gap: 4 }}>
          <Label>Enregistrés</Label>
          {done.map((d, i) => (
            <Text key={i} style={{ color: colors.success }}>
              ✓ {d}
            </Text>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 12, paddingBottom: 40 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  btn: {
    width: '31.5%',
    minHeight: 92,
    borderRadius: 14,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 8,
    gap: 6,
  },
  btnText: { color: colors.text, fontSize: 12, fontWeight: '700', textAlign: 'center' },
  input: {
    flex: 1,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    color: colors.text,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 15,
  },
});
