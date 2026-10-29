import { Component, onMounted, onPatched, signal, useProps } from "@odoo/owl";
import { TableResult } from "@odoo_chatbot/components/table_result/table_result";

export class MessageList extends Component {
    static template = "odoo_chatbot.MessageList";
    static components = { TableResult };
    props = useProps();
    listRef = signal.ref();

    setup() {
        onMounted(() => this.scrollToBottom());
        onPatched(() => this.scrollToBottom());
    }

    scrollToBottom() {
        const element = this.listRef();
        if (element) {
            element.scrollTop = element.scrollHeight;
        }
    }
}