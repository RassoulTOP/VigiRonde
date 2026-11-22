import { Stack } from 'expo-router';

import { PtiMonitor } from '@/components/PtiMonitor';
import { colors } from '@/components/ui';

export default function AppLayout() {
  return (
    <>
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.bg },
          headerTintColor: colors.text,
          headerTitleStyle: { fontWeight: '800' },
          headerShadowVisible: false,
          contentStyle: { backgroundColor: colors.bg },
          headerBackButtonDisplayMode: 'minimal',
        }}
      >
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen name="rondes" options={{ title: 'Rondes' }} />
        <Stack.Screen name="ronde" options={{ title: 'Ronde en cours' }} />
        <Stack.Screen name="scanner" options={{ presentation: 'fullScreenModal', headerShown: false }} />
        <Stack.Screen name="rapports" options={{ title: 'Rapports' }} />
        <Stack.Screen name="incident" options={{ title: 'Nouveau rapport', presentation: 'modal' }} />
        <Stack.Screen name="journal" options={{ title: 'Main courante' }} />
        <Stack.Screen name="evenement" options={{ title: 'Évènement simple', presentation: 'modal' }} />
        <Stack.Screen name="consignes" options={{ title: 'Consignes' }} />
        <Stack.Screen name="clefs" options={{ title: 'Clés' }} />
        <Stack.Screen name="visiteurs" options={{ title: 'Visiteurs' }} />
        <Stack.Screen name="pti" options={{ title: 'PTI · Travailleur isolé' }} />
        <Stack.Screen name="historique" options={{ title: 'Historique' }} />
        <Stack.Screen name="rapport/[id]" options={{ title: 'Rapport de ronde' }} />
      </Stack>
      <PtiMonitor />
    </>
  );
}
