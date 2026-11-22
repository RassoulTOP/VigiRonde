import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { ActivityIndicator, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { colors } from '@/components/ui';
import { PosteProvider } from '@/lib/poste';
import { SessionProvider, useSession } from '@/lib/session';

function RootStack() {
  const { ready, token } = useSession();
  if (!ready) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, justifyContent: 'center' }}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }}>
      <Stack.Protected guard={!!token}>
        <Stack.Screen name="(app)" />
      </Stack.Protected>
      <Stack.Protected guard={!token}>
        <Stack.Screen name="login" />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <PosteProvider>
          <StatusBar style="light" />
          <RootStack />
        </PosteProvider>
      </SessionProvider>
    </SafeAreaProvider>
  );
}
