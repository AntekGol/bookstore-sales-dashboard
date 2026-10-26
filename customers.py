IDENTITY_FIELDS = ["name", "address", "phone", "email"]


class UnionFind:
    def __init__(self, items):
        self.parent = {item: item for item in items}

    def find(self, item):
        root = item
        while self.parent[root] != root:
            root = self.parent[root]

        while self.parent[item] != root:
            next_item = self.parent[item]
            self.parent[item] = root
            item = next_item

        return root

    def union(self, first, second):
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root == second_root:
            return
        smaller_root = min(first_root, second_root)
        bigger_root = max(first_root, second_root)
        self.parent[bigger_root] = smaller_root


def assign_customer_ids(users):
    groups = UnionFind(users["id"].tolist())

    for changed_field in IDENTITY_FIELDS:
        matching_fields = [field for field in IDENTITY_FIELDS if field != changed_field]
        rows_with_all_fields = users.dropna(subset=matching_fields)

        for _, same_person in rows_with_all_fields.groupby(matching_fields):
            user_ids = same_person["id"].tolist()
            for other_id in user_ids[1:]:
                groups.union(user_ids[0], other_id)

    users = users.copy()
    users["customer_id"] = users["id"].map(groups.find)
    return users
