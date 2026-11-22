import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { Button, colors, Label, Muted, Row } from '@/components/ui';
import { useSession } from '@/lib/session';
import { INCIDENT_CATEGORIES, type IncidentCategory } from '@/lib/types';

const SEVERITIES = [
  { v: 1, label: 'Info', color: colors.muted },
  { v: 2, label: 'Faible', color: colors.primary },
  { v: 3, label: 'Moyen', color: colors.warning },
  { v: 4, label: 'Grave', color: '#f97316' },
  { v: 5, label: 'Critique', color: colors.danger },
];

/** Gravité proposée par défaut selon la catégorie (l'agent peut la changer). */
const DEFAULT_SEVERITY: Record<IncidentCategory, number> = {
  intrusion: 4,
  vol: 4,
  degradation: 3,
  incendie: 5,
  alarme_technique: 2,
  porte_ouverte: 2,
  personne_suspecte: 3,
  malaise: 5,
  autre: 2,
};

type Photo = { uri: string; mimeType?: string | null };

export default function IncidentScreen() {
  const { reportIncident, site } = useSession();
  const [category, setCategory] = useState<IncidentCategory | null>(null);
  const [severity, setSeverity] = useState(2);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [busy, setBusy] = useState(false);

  function pickCategory(c: IncidentCategory) {
    setCategory(c);
    setSeverity(DEFAULT_SEVERITY[c]);
    if (!title || Object.values(INCIDENT_CATEGORIES).includes(title as never)) setTitle(INCIDENT_CATEGORIES[c]);
  }

  async function addPhoto(fromCamera: boolean) {
    if (fromCamera) {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) return Alert.alert('Caméra refusée', 'Autorisez la caméra dans Réglages pour joindre des photos.');
    }
    const opts: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.6, exif: false };
    const res = fromCamera ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
    if (!res.canceled) setPhotos((p) => [...p, ...res.assets.map((a) => ({ uri: a.uri, mimeType: a.mimeType }))].slice(0, 6));
  }

  async function submit() {
    if (!category) return Alert.alert('Catégorie', 'Choisissez le type d’incident.');
    setBusy(true);
    try {
      await reportIncident({ category, severity, title: title.trim(), description: description.trim(), photos });
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      Alert.alert('Incident enregistré', 'Il sera transmis au superviseur dès que le réseau le permet.');
      router.back();
    } catch (e) {
      Alert.alert('Erreur', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
      <Muted>
        {site?.name} · la position GPS et l’heure sont ajoutées automatiquement.
      </Muted>

      <Label>Type d’incident</Label>
      <View style={s.chips}>
        {(Object.keys(INCIDENT_CATEGORIES) as IncidentCategory[]).map((c) => (
          <Pressable key={c} onPress={() => pickCategory(c)} style={[s.chip, category === c && s.chipOn]}>
            <Text style={[s.chipText, category === c && { color: '#fff' }]}>{INCIDENT_CATEGORIES[c]}</Text>
          </Pressable>
        ))}
      </View>

      <Label>Gravité</Label>
      <Row>
        {SEVERITIES.map((sv) => (
          <Pressable
            key={sv.v}
            onPress={() => setSeverity(sv.v)}
            style={[s.sev, { borderColor: sv.color }, severity === sv.v && { backgroundColor: sv.color }]}
          >
            <Text style={[s.sevNum, { color: severity === sv.v ? '#fff' : sv.color }]}>{sv.v}</Text>
            <Text style={[s.sevLabel, { color: severity === sv.v ? '#fff' : colors.muted }]}>{sv.label}</Text>
          </Pressable>
        ))}
      </Row>

      <Label>Titre</Label>
      <TextInput
        style={s.input}
        value={title}
        onChangeText={setTitle}
        placeholder="Ex. Porte du quai 3 ouverte"
        placeholderTextColor={colors.muted}
      />

      <Label>Ce qui s’est passé</Label>
      <TextInput
        style={[s.input, { minHeight: 130, textAlignVertical: 'top' }]}
        value={description}
        onChangeText={setDescription}
        placeholder="Décrivez avec vos mots : qui, quoi, où, quelles mesures prises. Astuce : touchez le micro du clavier pour dicter. Le rapport sera mis en forme automatiquement."
        placeholderTextColor={colors.muted}
        multiline
      />

      <Label>Photos ({photos.length}/6)</Label>
      <Row style={{ flexWrap: 'wrap' }}>
        {photos.map((p, i) => (
          <Pressable key={p.uri} onLongPress={() => setPhotos((ps) => ps.filter((_, j) => j !== i))}>
            <Image source={{ uri: p.uri }} style={s.thumb} />
          </Pressable>
        ))}
      </Row>
      {photos.length > 0 && <Muted style={{ fontSize: 12 }}>Appui long sur une photo pour la retirer.</Muted>}
      <Row>
        <Button title="Prendre une photo" icon="📷" variant="ghost" onPress={() => void addPhoto(true)} style={{ flex: 1 }} />
        <Button title="Galerie" icon="🖼" variant="ghost" onPress={() => void addPhoto(false)} style={{ flex: 1 }} />
      </Row>

      <Button
        title="Envoyer l’incident"
        variant="danger"
        big
        onPress={submit}
        loading={busy}
        disabled={!category || title.trim().length < 3 || description.trim().length < 3}
      />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 10, paddingBottom: 48 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: colors.card },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text, fontSize: 14, fontWeight: '600' },
  sev: { flex: 1, borderWidth: 1.5, borderRadius: 12, paddingVertical: 8, alignItems: 'center' },
  sevNum: { fontSize: 18, fontWeight: '900' },
  sevLabel: { fontSize: 11, fontWeight: '600' },
  input: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    color: colors.text,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 15,
  },
  thumb: { width: 92, height: 92, borderRadius: 12, backgroundColor: colors.card },
});
