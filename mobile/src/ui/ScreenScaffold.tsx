import type { PropsWithChildren } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

type ScreenScaffoldProps = PropsWithChildren<{
  eyebrow?: string;
  title: string;
  description?: string;
}>;

export function ScreenScaffold({ eyebrow, title, description, children }: ScreenScaffoldProps) {
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.header}>
        {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
        <Text style={styles.title}>{title}</Text>
        {description ? <Text style={styles.description}>{description}</Text> : null}
      </View>
      <View style={styles.body}>{children}</View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    minHeight: "100%",
    padding: 24,
    backgroundColor: "#faf8f4"
  },
  header: {
    gap: 10,
    marginBottom: 24
  },
  eyebrow: {
    color: "#9f2638",
    fontSize: 13,
    fontWeight: "700",
    textTransform: "uppercase"
  },
  title: {
    color: "#1f1b18",
    fontSize: 32,
    fontWeight: "800"
  },
  description: {
    color: "#6f655d",
    fontSize: 17,
    lineHeight: 25
  },
  body: {
    gap: 12
  }
});
