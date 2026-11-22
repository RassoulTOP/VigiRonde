import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import { useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button, colors, Muted } from '@/components/ui';
import { formatDistance } from '@/lib/geo';
import { useSession, type ScanResult } from '@/lib/session';

export default function Scanner() {
  const { scan } = useSession();
  const [permission, requestPermission] = useCameraPermissions();
  const [torch, setTorch] = useState(false);
  const [result, setResult] = useState<ScanResult | null>(null);
  const busy = useRef(false);

  async function onScanned(e: BarcodeScanningResult) {
    if (busy.current || result) return;
    busy.current = true;
    const r = await scan(e.data, 'qr');
    setResult(r);
    if (!r.ok) {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    } else if (r.valid) {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setTimeout(() => router.back(), 1400);
    } else {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    }
    busy.current = false;
  }

  if (!permission) return <View style={s.page} />;
  if (!permission.granted) {
    return (
      <SafeAreaView style={[s.page, { justifyContent: 'center', padding: 24, gap: 14 }]}>
        <Text style={s.title}>Accès à la caméra</Text>
        <Muted>La caméra sert uniquement à lire les QR codes des points de contrôle.</Muted>
        <Button title="Autoriser la caméra" onPress={requestPermission} />
        <Button title="Annuler" variant="ghost" onPress={() => router.back()} />
      </SafeAreaView>
    );
  }

  const tone = !result ? colors.primary : !result.ok ? colors.danger : result.valid ? colors.success : colors.warning;

  return (
    <View style={s.page}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        enableTorch={torch}
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={result ? undefined : onScanned}
      />
      <SafeAreaView style={s.overlay}>
        <Text style={s.hint}>{result ? ' ' : 'Visez le QR code du point de contrôle'}</Text>
        <View style={[s.frame, { borderColor: tone }]} />
        <View style={s.panel}>
          {result && !result.ok && (
            <>
              <Text style={[s.title, { color: colors.danger }]}>Code refusé</Text>
              <Muted>{result.message}</Muted>
            </>
          )}
          {result?.ok && (
            <>
              <Text style={[s.title, { color: tone }]}>
                {result.valid ? '✓ ' : '! '}
                {result.checkpoint.name}
              </Text>
              <Muted>
                {result.distance == null
                  ? 'Position GPS indisponible : passage enregistré et signalé'
                  : result.valid
                    ? `Contrôlé · ${formatDistance(result.distance)} du point`
                    : `Vous êtes à ${formatDistance(result.distance)} du point : ce passage sera signalé au superviseur`}
                {result.alreadyScanned ? ' · déjà contrôlé pendant cette ronde' : ''}
              </Muted>
            </>
          )}
          <View style={{ flexDirection: 'row', gap: 10 }}>
            {result && (!result.ok || !result.valid) ? (
              <Button title="Scanner à nouveau" onPress={() => setResult(null)} style={{ flex: 1 }} />
            ) : (
              <Button title={torch ? 'Éteindre la lampe' : 'Lampe'} icon="🔦" variant="ghost" onPress={() => setTorch((t) => !t)} style={{ flex: 1 }} />
            )}
            <Button title="Fermer" variant="ghost" onPress={() => router.back()} style={{ flex: 1 }} />
          </View>
        </View>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  page: { flex: 1, backgroundColor: '#000' },
  overlay: { flex: 1, justifyContent: 'space-between', alignItems: 'center', padding: 20 },
  hint: { color: '#fff', fontSize: 16, fontWeight: '700', marginTop: 12, textShadowColor: '#000', textShadowRadius: 6 },
  frame: { width: 250, height: 250, borderWidth: 4, borderRadius: 24 },
  panel: { alignSelf: 'stretch', backgroundColor: colors.card + 'f2', borderRadius: 18, padding: 16, gap: 10 },
  title: { color: colors.text, fontSize: 20, fontWeight: '800' },
});
