import { Component, useProps } from "@odoo/owl";

const BUCKETS = [
    ["today", "Today"],
    ["yesterday", "Yesterday"],
    ["previous_7_days", "Previous 7 days"],
    ["older", "Older"],
];

export class Sidebar extends Component {
    static template = "odoo_chatbot.Sidebar";
    props = useProps();

    get groups() {
        return BUCKETS.map(([key, label]) => ({
            key,
            label,
            items: this.props.conversations.filter((conv) => conv.bucket === key),
        })).filter((group) => group.items.length);
    }
}