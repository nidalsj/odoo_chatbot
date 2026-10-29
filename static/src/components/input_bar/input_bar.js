import { Component, onMounted, proxy, signal, useProps } from "@odoo/owl";

const MAX_INPUT_HEIGHT = 160;

export class InputBar extends Component {
    static template = "odoo_chatbot.InputBar";
    props = useProps();
    draft = signal("");
    inputRef = signal.ref();

    setup() {
        this.state = proxy({ confirming: false });
        onMounted(() => {
            const element = this.inputRef();
            if (element) {
                element.focus();
            }
        });
    }

    get canSend() {
        return !this.props.sending && this.draft().trim().length > 0;
    }

    onKeydown(event) {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            this.submit();
        }
    }

    onInput() {
        const element = this.inputRef();
        if (element) {
            element.style.height = "auto";
            element.style.height = `${Math.min(element.scrollHeight, MAX_INPUT_HEIGHT)}px`;
        }
    }

    submit() {
        const text = this.draft().trim();
        if (!text || this.props.sending) {
            return;
        }
        this.draft.set("");
        this.state.confirming = false;
        const element = this.inputRef();
        if (element) {
            element.style.height = "auto";
        }
        this.props.onSend(text);
    }

    askDelete() {
        if (this.props.canDelete && !this.props.sending) {
            this.state.confirming = true;
        }
    }

    cancelDelete() {
        this.state.confirming = false;
    }

    confirmDelete() {
        this.state.confirming = false;
        this.props.onDelete();
    }
}