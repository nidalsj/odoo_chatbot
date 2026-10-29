import { Component, types as t, useProps } from "@odoo/owl";

export class TableResult extends Component {
    static template = "odoo_chatbot.TableResult";
    props = useProps({ result: t.object() });
}