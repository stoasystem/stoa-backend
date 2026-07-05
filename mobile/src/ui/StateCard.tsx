import { StyleSheet, Text, View } from "react-native";

type StateCardProps = {
  title: string;
  body: string;
};

export function StateCard({ title, body }: StateCardProps) {
  return (
    <View style={styles.card}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.body}>{body}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: "#ded4ca",
    borderRadius: 8,
    padding: 16,
    backgroundColor: "#fffdf9"
  },
  title: {
    color: "#1f1b18",
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 6
  },
  body: {
    color: "#6f655d",
    fontSize: 15,
    lineHeight: 22
  }
});
