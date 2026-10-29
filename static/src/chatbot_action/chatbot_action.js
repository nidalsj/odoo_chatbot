import { Component, onMounted, onWillDestroy, proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

import { InputBar } from "@odoo_chatbot/components/input_bar/input_bar";
import { MessageList } from "@odoo_chatbot/components/message_list/message_list";
import { Sidebar } from "@odoo_chatbot/components/sidebar/sidebar";

const MODEL = "chatbot.conversation";
const MOBILE_QUERY = "(max-width: 767.98px)";

function errorText(error) {
    return (
        (error && error.data && error.data.message) ||
        (error && error.message) ||
        "Something went wrong. Please try again."
    );
}

export class ChatbotAction extends Component {
    static template = "odoo_chatbot.ChatbotAction";
    static components = { Sidebar, MessageList, InputBar };

    setup() {
        this.orm = useService("orm");
        const mobileQuery = window.matchMedia(MOBILE_QUERY);
        this.state = proxy({
            conversations: [],
            activeId: false, // false = a new chat that is not saved yet
            messages: [],
            loading: true,
            sending: false,
            notice: "",
            isMobile: mobileQuery.matches,
            sidebarOpen: !mobileQuery.matches,
        });

        const onBreakpoint = (event) => {
            this.state.isMobile = event.matches;
            this.state.sidebarOpen = !event.matches;
        };
        mobileQuery.addEventListener("change", onBreakpoint);
        onWillDestroy(() => mobileQuery.removeEventListener("change", onBreakpoint));
        onMounted(() => this.loadConversations());
    }

    async loadConversations() {
        try {
            this.state.conversations = await this.orm.call(MODEL, "get_conversations", []);
        } catch (error) {
            this.state.notice = errorText(error);
        } finally {
            this.state.loading = false;
        }
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
    }

    dismissNotice() {
        this.state.notice = "";
    }

    newChat() {
        if (this.state.sending) {
            return;
        }
        this.state.activeId = false;
        this.state.messages = [];
        this.state.notice = "";
        if (this.state.isMobile) {
            this.state.sidebarOpen = false;
        }
    }

    async selectConversation(id) {
        if (this.state.sending || id === this.state.activeId) {
            return;
        }
        this.state.activeId = id;
        this.state.messages = [];
        this.state.notice = "";
        if (this.state.isMobile) {
            this.state.sidebarOpen = false;
        }
        try {
            const messages = await this.orm.call(MODEL, "get_messages", [id]);
            if (this.state.activeId === id) {
                this.state.messages = messages;
            }
        } catch (error) {
            this.state.notice = errorText(error);
        }
    }

    async send(text) {
        if (this.state.sending) {
            return;
        }
        const conversationId = this.state.activeId;
        const tempId = `local-${Date.now()}`;
        this.state.notice = "";
        this.state.sending = true;
        this.state.messages.push({ id: tempId, role: "user", text, status: "ok", result: false });
        try {
            const out = await this.orm.call(MODEL, "send_message", [conversationId, text]);
            const conv = out.conversation;
            const index = this.state.conversations.findIndex((c) => c.id === conv.id);
            if (index === -1) {
                this.state.conversations.unshift(conv);
            } else {
                this.state.conversations[index] = conv;
            }
            this.state.activeId = conv.id;
            this.state.messages = [
                ...this.state.messages.filter((m) => m.id !== tempId),
                ...out.messages,
            ];
        } catch (error) {
            this.state.messages.push({
                id: `local-error-${Date.now()}`,
                role: "bot",
                text: errorText(error),
                status: "error",
                result: false,
            });
        } finally {
            this.state.sending = false;
        }
    }

    async deleteCurrent() {
        if (this.state.sending) {
            return;
        }
        const id = this.state.activeId;
        if (id) {
            try {
                await this.orm.call(MODEL, "unlink", [[id]]);
            } catch (error) {
                this.state.notice = errorText(error);
                return;
            }
            this.state.conversations = this.state.conversations.filter((c) => c.id !== id);
        }
        this.state.activeId = false;
        this.state.messages = [];
    }
}

registry.category("actions").add("odoo_chatbot.chat_action", ChatbotAction);