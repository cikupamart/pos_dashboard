/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onWillStart, onPatched } from "@odoo/owl";

function firstDayOfMonth() {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}
function today() {
    return new Date().toISOString().slice(0, 10);
}

export class PosDashboard extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.canvas1 = useRef("chartMain");
        this.canvas2 = useRef("chartSecondary");
        this._chart1 = null;
        this._chart2 = null;
        this._lastRenderedKey = null;

        const params = this.props.action?.params || {};
        this.state = useState({
            reportKey: params.report_key || "direksi",
            dateFrom: params.date_from || firstDayOfMonth(),
            dateTo: params.date_to || today(),
            configIds: params.config_ids || [],
            userIds: params.user_ids || [],
            meta: { reports: [], configs: [], users: [] },
            data: null,
            loading: false,
        });

        onWillStart(async () => {
            this.state.meta = await this.rpc("/pos_dashboard/meta", {});
            await this.loadData();
        });

        onPatched(() => this.renderCharts());
    }

    get reportLabel() {
        const found = this.state.meta.reports.find((r) => r.key === this.state.reportKey);
        return found ? found.label : this.state.reportKey;
    }

    async loadData() {
        this.state.loading = true;
        try {
            this.state.data = await this.rpc("/pos_dashboard/data", {
                report_key: this.state.reportKey,
                date_from: this.state.dateFrom,
                date_to: this.state.dateTo,
                config_ids: this.state.configIds,
                user_ids: this.state.userIds,
                limit: 200,
                offset: 0,
            });
        } catch (e) {
            this.notification.add("Gagal memuat data laporan.", { type: "danger" });
            this.state.data = null;
        }
        this.state.loading = false;
    }

    onFilterChange(field, ev) {
        this.state[field] = ev.target.value;
    }
    onMultiChange(field, ev) {
        const values = Array.from(ev.target.selectedOptions).map((o) => parseInt(o.value));
        this.state[field] = values;
    }
    async onApply() {
        await this.loadData();
    }

    exportUrl(kind) {
        const p = new URLSearchParams({
            report_key: this.state.reportKey,
            date_from: this.state.dateFrom,
            date_to: this.state.dateTo,
            config_ids: JSON.stringify(this.state.configIds),
            user_ids: JSON.stringify(this.state.userIds),
        });
        if (kind === "xlsx") {
            return "/pos_dashboard/export/xlsx?" + p.toString();
        }
        return "#";
    }
    onExportXlsx() {
        window.open(this.exportUrl("xlsx"), "_self");
    }

    renderCharts() {
        if (!window.Chart || !this.state.data) return;
        const data = this.state.data;
        const key = JSON.stringify([this.state.reportKey, this.state.dateFrom, this.state.dateTo, data]);
        if (this._lastRenderedKey === key) return;
        this._lastRenderedKey = key;

        const mkChart = (canvasEl, existing, chartData, type) => {
            if (!canvasEl || !chartData || !chartData.labels || !chartData.labels.length) {
                if (existing) existing.destroy();
                return null;
            }
            if (existing) existing.destroy();
            return new window.Chart(canvasEl, {
                type: type,
                data: {
                    labels: chartData.labels,
                    datasets: chartData.datasets.map((ds, i) => ({
                        label: ds.label,
                        data: ds.data,
                        backgroundColor: type === "pie"
                            ? chartData.labels.map((_, j) => `hsl(${(j * 47) % 360},65%,55%)`)
                            : `hsl(${(i * 97) % 360},65%,55%)`,
                        borderColor: `hsl(${(i * 97) % 360},65%,45%)`,
                        fill: type === "line" ? false : true,
                    })),
                },
                options: { responsive: true, maintainAspectRatio: false },
            });
        };

        if (data.chart) {
            this._chart1 = mkChart(this.canvas1.el, this._chart1, data.chart, "bar");
        } else if (data.chart_trend) {
            this._chart1 = mkChart(this.canvas1.el, this._chart1, data.chart_trend, "line");
            this._chart2 = mkChart(this.canvas2.el, this._chart2, data.chart_category, "pie");
        }
    }
}
PosDashboard.template = "pos_dashboard_reports.Dashboard";
PosDashboard.components = {};

registry.category("actions").add("pos_dashboard_client_action", PosDashboard);
