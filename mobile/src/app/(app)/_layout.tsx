import { Stack } from 'expo-router';

import { colors } from '@/components/ui';

export default function AppLayout() {
  return (
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
      <Stack.Screen name="index" options={{ title: 'VigiRonde' }} />
      <Stack.Screen name="ronde" options={{ title: 'Ronde en cours', headerBackVisible: true }} />
      <Stack.Screen name="scanner" options={{ title: 'Scanner un point', presentation: 'fullScreenModal', headerShown: false }} />
      <Stack.Screen name="incident" options={{ title: 'Signaler un incident', presentation: 'modal' }} />
      <Stack.Screen name="historique" options={{ title: 'Historique' }} />
      <Stack.Screen name="rapport/[id]" options={{ title: 'Rapport de ronde' }} />
    </Stack>
  );
}
