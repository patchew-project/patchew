% include('templates/header.tpl', title='Series')

<style type="text/css">
.series-status a:hover {
    text-decoration: none;
}

</style>

<form class="form-horizontal" role="form" method="GET" action="/">
    <div class="form-group col-sm-4">
        <div class="input-group">
            <input type="search" class="form-control" name="search" placeholder="Search" value="{{search}}">
            <span class="input-group-btn">
                <input type="submit" class="btn btn-default" value="Search"/>
            </span>
        </div>
    </div>
</form>

<table class="table table-condensed table-striped">
    <tr>
        <th colspan="2"></th>
        <th>Subject</th>
        <th>Author</th>
        <th>Age</th>
    </tr>
    % for s in series:
        <tr>
            <td>
                %if s.get('reviewed'):
                    <span title="Reviewers: {{", ".join([x for x, y in s['reviewers']])}}" class="label label-success">Reviewed</span>
                %elif s.get('repliers'):
                    <span title="Have replies from: {{", ".join([x for x, y in s['repliers']])}}" class="label label-info">Replied</span>
                %end
            </td>
            <td class="series-status">
                %if s.get('merged'):
                    <a href="/testing/log/{{s['message-id']}}">
                        <span title="{{s['testing-end-time']}}" class="label label-primary timestamp">Merged</span>
                    </a>
                %elif s.get('obsoleted-by'):
                    <a href="/series/{{s['obsoleted-by']}}">
                        <span title="There is a new version, click to see: {{s['obsoleted-by-subject']}}" class="label label-default">Old version</span>
                    </a>
                %elif s.get('testing-started'):
                    <a href="/testing/manual/{{s['message-id']}}">
                        <span title="{{s['testing-start-time']}}" class="label label-warning timestamp">Testing</span>
                    </a>
                %elif s['testing-passed'] == True:
                    <a href="/testing/log/{{s['message-id']}}">
                        <span title="{{s['testing-end-time']}}" class="label label-success timestamp">Pass</span>
                    </a>
                %elif s['testing-passed'] == False:
                    <a href="/testing/log/{{s['message-id']}}">
                        <span title="{{s['testing-end-time']}}" class="label label-danger timestamp">Failed {{s['testing-failure-step']}}</span>
                    </a>
                %end
            </td>
            <td>
                <a name="{{s['message-id']}}"></a>
                <a href="/series/{{s['message-id']}}">{{s['subject']}}</a>
            </td>
            <td><span title="{{s['author-address']}}">{{s['author']}}</span></td>
            <td><span class="timestamp" title="{{s['date']}}">{{s['age']}}</span></td>
        </tr>
    %end
</table>

<nav>
    <ul class="pagination">
        %dot = True
        %for i in range(0, totalpages):
            % between = lambda v, s, e: v >= s and v <= e
            % show = between(i, 0, 9)
            % show = show or between(i, totalpages - 5, totalpages - 1)
            % show = show or between(i, curpage - 2, curpage + 3)
            % if show:
                <li class="{{"active" if curpage == i else ""}}">
                    <a href="/index/{{i * pagesize}}-{{(i + 1) * pagesize}}{{"?search="+search if search else ""}}">{{i + 1}}</a>
                </li>
                %dot = True
            %elif dot:
                <li class="disabled">
                    <a href="#">...</a>
                </li>
                %dot = False
            %end
        %end
    </ul>
</nav>


<script language="javascript" type="text/javascript">

function main() {
    $(".timestamp").each(function (i, o) {
        $(o).attr("title", new Date(1000 * $(o).attr("title")));
    });
}

$(main);

</script>
% include('templates/footer.tpl')
