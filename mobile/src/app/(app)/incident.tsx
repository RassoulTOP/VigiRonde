import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Alert, Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { Badge, Button, colors, Label, Muted, Row } from '@/components/ui';
import { usePoste } from '@/lib/poste';
import { useSession } from '@/lib/session';
import { INCIDENT_CATEGORIES, REPORT_CATEGORIES, type IncidentCategory, type TemplateField } from '@/lib/types';

const SEVERITIES = [
  { v: 1, label: 'Info', color: colors.muted },
  { v: 2, label: 'Faible', color: colors.primary },
  { v: 3, label: 'Moyen', color: colors.warning },
  { v: 4, label: 'Grave', color: '#f97316' },
  { v: 5, label: 'Critique', color: colors.danger },
];

const DEFAULT_SEVERITY: Record<IncidentCategory, number> = {
  intrusion: 4, vol: 4, degradation: 3, incendie: 5, alarme_technique: 2,
  porte_ouverte: 2, personne_suspecte: 3, malaise: 5, autre: 2,
};

type Photo = { uri: string; mimeType?: string | null };
type Answers = Record<string, string | boolean | string[]>;

function FieldInput({ f, value, onChange }: { f: TemplateField; value: Answers[string] | undefined; onChange: (v: Answers[string]) => void }) {
  if (f.type === 'boolean') {
    return (
      <Row>
        {[true, false].map((b) => (
          <Pressable key={String(b)} onPress={() => onChange(b)} style={[s.chip, value === b && s.chipOn]}>
            <Text style={[s.chipText, value === b && { color: '#fff' }]}>{b ? 'Oui' : 'Non'}</Text>
          </Pressable>
        ))}
      </Row>
    );
  }
  if (f.type === 'select' || f.type === 'multiselect') {
    const multi = f.type === 'multiselect';
    const sel = multi ? ((value as string[]) ?? []) : value;
    return (
      <View style={s.chips}>
        {(f.options ?? []).map((o) => {
          const on = multi ? (sel as string[]).includes(o) : sel === o;
          return (
            <Pressable
              key={o}
              onPress={() =>
                onChange(multi ? (on ? (sel as string[]).filter((x) => x !== o) : [...(sel as string[]), o]) : o)
              }
              style={[s.chip, on && s.chipOn]}
            >
              <Text style={[s.chipText, on && { color: '#fff' }]}>{o}</Text>
            </Pressable>
          );
        })}
      </View>
    );
  }
  return (
    <TextInput
      style={[s.input, f.type === 'textarea' && { minHeight: 80, textAlignVertical: 'top' }]}
      value={(value as string) ?? ''}
      onChangeText={onChange}
      placeholder={f.type === 'time' ? 'HH:MM' : f.help ?? ''}
      placeholderTextColor={colors.muted}
      multiline={f.type === 'textarea'}
      keyboardType={f.type === 'number' ? 'numeric' : f.type === 'time' ? 'numbers-and-punctuation' : 'default'}
      autoCapitalize={f.key === 'plaque' ? 'characters' : 'sentences'}
    />
  );
}

export default function ReportForm() {
  const { template: templateId } = useLocalSearchParams<{ template?: string }>();
  const { reportIncident, site } = useSession();
  const { reportTemplates, draftReport } = usePoste();
  const tpl = reportTemplates.find((t) => t.id === templateId) ?? null;

  const [category, setCategory] = useState<IncidentCategory | null>(tpl?.incident_category ?? null);
  const [severity, setSeverity] = useState(tpl?.default_severity ?? 2);
  const [title, setTitle] = useState(tpl?.name ?? '');
  const [description, setDescription] = useState('');
  const [answers, setAnswers] = useState<Answers>({});
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [draft, setDraft] = useState<{ text: string; source: 'ia' | 'modele' } | null>(null);
  const [drafting, setDrafting] = useState(false);
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

  const missing = (tpl?.fields ?? []).filter((f) => {
    const v = answers[f.key];
    return f.required && (v === undefined || v === '' || (Array.isArray(v) && !v.length));
  });

  async function makeDraft() {
    setDrafting(true);
    try {
      setDraft(await draftReport({ template_id: tpl?.id ?? null, title: title.trim(), description: description.trim(), answers, severity }));
    } catch {
      Alert.alert('Hors réseau', 'La mise en forme se fera automatiquement à l’arrivée du rapport au serveur.');
    } finally {
      setDrafting(false);
    }
  }

  async function submit() {
    const cat = category ?? tpl?.incident_category;
    if (!cat) return Alert.alert('Catégorie', 'Choisissez le type d’incident.');
    if (missing.length) return Alert.alert('Champs obligatoires', missing.map((f) => `• ${f.label}`).join('\n'));
    setBusy(true);
    try {
      await reportIncident({
        category: cat,
        severity,
        title: title.trim(),
        description: description.trim(),
        photos,
        templateId: tpl?.id ?? null,
        answers,
        reportAi: draft?.text.trim() || null,
      });
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      Alert.alert('Rapport enregistré', 'Il sera transmis au superviseur dès que le réseau le permet.');
      router.back();
    } catch (e) {
      Alert.alert('Erreur', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
      {tpl ? (
        <Row>
          <Text style={{ fontSize: 30 }}>{tpl.icon ?? '📋'}</Text>
          <View style={{ flex: 1, gap: 4 }}>
            <Text style={s.tplName}>{tpl.name}</Text>
            <Badge label={REPORT_CATEGORIES[tpl.category]} tone="primary" />
          </View>
        </Row>
      ) : (
        <>
          <Label>Type d’incident</Label>
          <View style={s.chips}>
            {(Object.keys(INCIDENT_CATEGORIES) as IncidentCategory[]).map((c) => (
              <Pressable key={c} onPress={() => pickCategory(c)} style={[s.chip, category === c && s.chipOn]}>
                <Text style={[s.chipText, category === c && { color: '#fff' }]}>{INCIDENT_CATEGORIES[c]}</Text>
              </Pressable>
            ))}
          </View>
        </>
      )}
      <Muted>{site?.name} · heure et position GPS ajoutées automatiquement.</Muted>

      {tpl?.fields.map((f) => (
        <View key={f.key} style={{ gap: 6 }}>
          <Label>
            {f.label}
            {f.required ? ' *' : ''}
          </Label>
          <FieldInput f={f} value={answers[f.key]} onChange={(v) => setAnswers((a) => ({ ...a, [f.key]: v }))} />
        </View>
      ))}

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

      <Label>Objet</Label>
      <TextInput style={s.input} value={title} onChangeText={setTitle} placeholder="Ex. Porte du quai 3 ouverte" placeholderTextColor={colors.muted} />

      <Label>Ce qui s’est passé</Label>
      <TextInput
        style={[s.input, { minHeight: 130, textAlignVertical: 'top' }]}
        value={description}
        onChangeText={(t) => {
          setDescription(t);
          setDraft(null);
        }}
        placeholder="Racontez avec vos mots (touchez le micro du clavier pour dicter) : ce que vous avez vu, ce que vous avez fait, qui a été prévenu."
        placeholderTextColor={colors.muted}
        multiline
      />

      {draft ? (
        <View style={s.draft}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Label>{draft.source === 'ia' ? '✨ Rapport rédigé par l’IA — relisez' : 'Rapport mis en forme — relisez'}</Label>
            <Pressable onPress={() => setDraft(null)}>
              <Text style={{ color: colors.muted }}>Retirer</Text>
            </Pressable>
          </Row>
          <TextInput
            style={[s.input, { minHeight: 220, textAlignVertical: 'top', fontSize: 13 }]}
            value={draft.text}
            onChangeText={(t) => setDraft({ ...draft, text: t })}
            multiline
          />
        </View>
      ) : (
        <Pressable
          onPress={makeDraft}
          disabled={drafting || title.trim().length < 3 || description.trim().length < 3}
          style={[s.ai, (title.trim().length < 3 || description.trim().length < 3) && { opacity: 0.4 }]}
        >
          {drafting ? <ActivityIndicator color="#c4b5fd" /> : <Text style={s.aiText}>✨ Rédiger le rapport professionnel</Text>}
        </Pressable>
      )}

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
        <Button title="Photo" icon="📷" variant="ghost" onPress={() => void addPhoto(true)} style={{ flex: 1 }} />
        <Button title="Galerie" icon="🖼" variant="ghost" onPress={() => void addPhoto(false)} style={{ flex: 1 }} />
      </Row>

      <Button
        title="Envoyer le rapport"
        variant="danger"
        big
        onPress={submit}
        loading={busy}
        disabled={(!category && !tpl) || title.trim().length < 3 || description.trim().length < 3}
      />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 10, paddingBottom: 48 },
  tplName: { color: colors.text, fontSize: 20, fontWeight: '900' },
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
  draft: { gap: 6, borderWidth: 1, borderColor: '#7c3aed', borderRadius: 14, padding: 10, backgroundColor: '#1e1b4b55' },
  ai: { borderWidth: 1.5, borderColor: '#7c3aed', borderRadius: 14, paddingVertical: 14, alignItems: 'center', backgroundColor: '#2e1065' },
  aiText: { color: '#ddd6fe', fontWeight: '800', fontSize: 15 },
  thumb: { width: 92, height: 92, borderRadius: 12, backgroundColor: colors.card },
});
