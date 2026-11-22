/**
 * Surveillance PTI (protection du travailleur isolé) pendant le service :
 * - chute : choc violent (> 2,5 g) suivi d'une immobilité de quelques secondes ;
 * - immobilité : aucun mouvement pendant le délai choisi par l'agent.
 * Une pré-alarme (vibrations, compte à rebours) laisse 20 s à l'agent pour dire « Je vais bien » ;
 * sans réponse, l'alerte part au PC sécurité avec la position GPS.
 *
 * Démonstration : un vrai DATI doit être certifié et fonctionner écran verrouillé (development build).
 */
import { Accelerometer } from 'expo-sensors';
import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, Vibration, View } from 'react-native';

import { usePoste } from '@/lib/poste';
import { useSession } from '@/lib/session';
import type { AlertKind } from '@/lib/types';

const COUNTDOWN_S = 20;
const FALL_G = 2.5;
const MOVE_THRESHOLD_G = 0.06;

export function PtiMonitor() {
  const { shift } = useSession();
  const { ptiEnabled, ptiDelaySec, pause, alert, raiseAlert } = usePoste();
  const [pre, setPre] = useState<{ kind: AlertKind; left: number } | null>(null);
  const lastMove = useRef(0);
  const fallAt = useRef<number | null>(null);
  const last = useRef<{ x: number; y: number; z: number } | null>(null);

  const alertActive = alert && (alert.status === 'active' || alert.status === 'prise_en_charge');
  const watching = shift?.status === 'en_cours' && ptiEnabled && !pause && !alertActive && !pre;

  // Capteur de mouvement
  useEffect(() => {
    if (!watching) return;
    lastMove.current = Date.now();
    fallAt.current = null;
    Accelerometer.setUpdateInterval(200);
    const sub = Accelerometer.addListener(({ x, y, z }) => {
      const now = Date.now();
      const g = Math.sqrt(x * x + y * y + z * z);
      const p = last.current;
      const delta = p ? Math.abs(x - p.x) + Math.abs(y - p.y) + Math.abs(z - p.z) : 0;
      last.current = { x, y, z };
      if (g > FALL_G) fallAt.current = now;
      if (delta > MOVE_THRESHOLD_G) {
        // Après une chute, on attend 4 s d'immobilité ; un mouvement normal annule le soupçon
        if (fallAt.current && now - fallAt.current > 1500) fallAt.current = null;
        lastMove.current = now;
      }
    });
    const timer = setInterval(() => {
      const now = Date.now();
      if (fallAt.current && now - fallAt.current > 4000 && now - lastMove.current > 3000) {
        setPre({ kind: 'chute', left: COUNTDOWN_S });
      } else if (now - lastMove.current > ptiDelaySec * 1000) {
        setPre({ kind: 'immobilite', left: COUNTDOWN_S });
      }
    }, 1000);
    return () => {
      sub.remove();
      clearInterval(timer);
    };
  }, [watching, ptiDelaySec]);

  // Pré-alarme : vibrations + compte à rebours ; à zéro, l'alerte part
  const preKind = pre?.kind;
  useEffect(() => {
    if (!preKind) return;
    Vibration.vibrate([0, 700, 500], true);
    let left = COUNTDOWN_S;
    const t = setInterval(() => {
      left -= 1;
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      if (left > 0) {
        setPre((p) => (p ? { ...p, left } : p));
        return;
      }
      clearInterval(t);
      Vibration.cancel();
      setPre(null);
      void raiseAlert(preKind).then(() => router.push('/pti'));
    }, 1000);
    return () => {
      clearInterval(t);
      Vibration.cancel();
    };
  }, [preKind, raiseAlert]);

  function imOk() {
    lastMove.current = Date.now();
    fallAt.current = null;
    setPre(null);
  }

  if (!pre) return null;
  return (
    <Modal visible animationType="fade" presentationStyle="fullScreen">
      <View style={s.page}>
        <Text style={s.kicker}>PROTECTION TRAVAILLEUR ISOLÉ</Text>
        <Text style={s.title}>{pre.kind === 'chute' ? 'Chute détectée' : 'Aucun mouvement détecté'}</Text>
        <Text style={s.count}>{Math.max(0, pre.left)}</Text>
        <Text style={s.sub}>Sans réponse, une alerte sera envoyée au PC sécurité avec votre position.</Text>
        <Pressable onPress={imOk} style={({ pressed }) => [s.ok, pressed && { opacity: 0.85 }]}>
          <Text style={s.okText}>JE VAIS BIEN</Text>
        </Pressable>
        <Pressable
          onPress={() => {
            setPre(null);
            void raiseAlert(pre.kind === 'chute' ? 'chute' : 'sos').then(() => router.push('/pti'));
          }}
          style={s.now}
        >
          <Text style={s.nowText}>Envoyer l’alerte maintenant</Text>
        </Pressable>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  page: { flex: 1, backgroundColor: '#b91c1c', alignItems: 'center', justifyContent: 'center', padding: 28, gap: 18 },
  kicker: { color: '#fecaca', fontWeight: '800', letterSpacing: 1.5, fontSize: 13 },
  title: { color: '#fff', fontSize: 30, fontWeight: '900', textAlign: 'center' },
  count: { color: '#fff', fontSize: 110, fontWeight: '900', fontVariant: ['tabular-nums'] },
  sub: { color: '#fee2e2', fontSize: 16, textAlign: 'center' },
  ok: { backgroundColor: '#fff', borderRadius: 22, paddingVertical: 26, alignSelf: 'stretch', alignItems: 'center', marginTop: 12 },
  okText: { color: '#b91c1c', fontSize: 26, fontWeight: '900', letterSpacing: 1 },
  now: { padding: 12 },
  nowText: { color: '#fff', textDecorationLine: 'underline', fontSize: 15 },
});
