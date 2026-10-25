function categoryManager() {
    return {
        newCategory: '',
        error: '',
        confirming: null,
        counts: {},
        busy: false,

        init() {
            this.refresh();
        },

        async refresh() {
            // get the amount of categories
            try {
                this.counts = await simpleApiFetch('/api/chats/categories/count') ?? {};
            } catch (err) {
                this.counts = {};
            }
        },

        countFor(category) {
            return this.counts[category] ?? 0;
        },

        async add() {
            this.error = '';
            const name = this.newCategory.trim().toLowerCase();

            this.busy = true;
            try {
                await simpleApiPost('/api/chats/categories/create', { name: name });

                await Alpine.store('chat').reloadCategories();
                await Alpine.store('chat').reloadChats();
                await Alpine.store('chat').reloadChat();

                this.newCategory = '';
                await this.refresh();
            } catch (e) {
                this.error = typeof e === 'string' ? e : 'failed to create category';
            } finally {
                this.busy = false;
            }
        },

        async confirmDelete(name) {
            this.busy = true;
            try {
                await Alpine.store('chat').deleteCategory(name);
                this.confirming = null;
                await this.refresh();
            } catch (e) {
                this.error = typeof e === 'string' ? e : 'failed to delete category';
            } finally {
                this.busy = false;
            }
        }
    };
}
