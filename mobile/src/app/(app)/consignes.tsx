import * as Haptics from 'expo-haptics';
import { ScrollView, StyleSheet, Text } from 'react-native';

import { Badge, Button, Card, colors, fmtDateTime, Muted, Row } from '@/components/ui';
import { usePoste } from '@/lib/poste';

export default function Consignes() {
  const { instructions, ackInstruction } = usePoste();
  const sorted = [...instructions].sort((a, b) => Number(!!a.acked_at) - Number(!!b.acked_at));

  return (
    <ScrollView contentContainerStyle={s.page}>
      {sorted.map((i) => (
        <Card key={i.id} style={!i.acked_at && i.important ? { borderColor: colors.warning } : undefined}>
          <Row style={{ flexWrap: 'wrap' }}>
            {i.important && <Badge label="Important" tone="warning" />}
            {i.valid_to && <Badge label={`Jusqu’au ${fmtDateTime(i.valid_to)}`} tone="primary" />}
            {i.acked_at ? <Badge label={`Lu le ${fmtDateTime(i.acked_at)}`} tone="success" /> : <Badge label="Non lue" tone="danger" />}
          </Row>
          <Text style={s.title}>{i.title}</Text>
          <Text style={s.body}>{i.body}</Text>
          {!i.acked_at && (
            <Button
              title="Lu et compris"
              icon="✓"
              variant="success"
              onPress={() => {
                void ackInstruction(i.id);
                void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
              }}
            />
          )}
        </Card>
      ))}
      {!instructions.length && <Muted>Aucune consigne pour ce site.</Muted>}
      <Muted style={{ fontSize: 12 }}>La validation est horodatée et inscrite en main courante.</Muted>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, gap: 12, paddingBottom: 40 },
  title: { color: colors.text, fontSize: 18, fontWeight: '800' },
  body: { color: colors.text, fontSize: 15, lineHeight: 22 },
});
