import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { colors, Muted } from '@/components/ui';
import { usePoste } from '@/lib/poste';
import { REPORT_CATEGORIES, type ReportCategory } from '@/lib/types';

type Tab = 'tous' | ReportCategory;

export default function Rapports() {
  const { reportTemplates } = usePoste();
  const [tab, setTab] = useState<Tab>('tous');
  const cats = [...new Set(reportTemplates.map((t) => t.category))];
  const list = reportTemplates.filter((t) => tab === 'tous' || t.category === tab);

  return (
    <View style={{ flex: 1 }}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.tabs} style={{ flexGrow: 0 }}>
        {(['tous', ...cats] as Tab[]).map((c) => (
          <Pressable key={c} onPress={() => setTab(c)} style={[s.tab, tab === c && s.tabOn]}>
            <Text style={[s.tabText, tab === c && { color: '#fff' }]}>{c === 'tous' ? 'Tous' : REPORT_CATEGORIES[c]}</Text>
          </Pressable>
        ))}
      </ScrollView>
      <ScrollView contentContainerStyle={s.page}>
        {list.map((t) => (
          <Pressable
            key={t.id}
            onPress={() => router.push({ pathname: '/incident', params: { template: t.id } })}
            style={({ pressed }) => [s.item, pressed && { opacity: 0.8 }]}
          >
            <Text style={{ fontSize: 26 }}>{t.icon ?? '📋'}</Text>
            <View style={{ flex: 1 }}>
              <Text style={s.name}>{t.name}</Text>
              <Muted style={{ fontSize: 12 }}>
                {REPORT_CATEGORIES[t.category]} · {t.fields.length} champ(s)
              </Muted>
            </View>
            <Text style={{ color: colors.muted, fontSize: 22 }}>›</Text>
          </Pressable>
        ))}
        <Pressable onPress={() => router.push('/incident')} style={[s.item, { borderStyle: 'dashed' }]}>
          <Text style={{ fontSize: 26 }}>✍️</Text>
          <View style={{ flex: 1 }}>
            <Text style={s.name}>Rapport libre</Text>
            <Muted style={{ fontSize: 12 }}>Sans modèle : catégorie, description, photos</Muted>
          </View>
        </Pressable>
        {!reportTemplates.length && <Muted>Modèles indisponibles hors réseau : utilisez le rapport libre.</Muted>}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  tabs: { paddingHorizontal: 16, paddingVertical: 10, gap: 8 },
  tab: { borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 },
  tabOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  tabText: { color: colors.text, fontWeight: '700' },
  page: { padding: 16, paddingTop: 4, gap: 10, paddingBottom: 40 },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    backgroundColor: colors.card,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 14,
  },
  name: { color: colors.text, fontSize: 16, fontWeight: '800' },
});
